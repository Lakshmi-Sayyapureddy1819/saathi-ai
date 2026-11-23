<#
Deploy / update / tear down the Saathi Care AI demo stack on AWS (Windows PowerShell 5.1+).

  .\deploy\deploy.ps1 -Action Deploy                      first deploy (creates secret, stack, uploads source, waits)
  .\deploy\deploy.ps1 -Action Update                      ship current source to the running host and restart containers
  .\deploy\deploy.ps1 -Action Status                      stack status + outputs
  .\deploy\deploy.ps1 -Action Teardown -ConfirmTeardown   delete the stack (and its data). Never runs without the switch.

Safety: secret VALUES are read from .env into a temp file, sent to Secrets Manager, and the temp file is deleted. They are
never printed, put in CloudFormation parameters, tags, Git, or the source tarball. Nothing outside this stack is modified.
#>
[CmdletBinding()]
param(
    [ValidateSet("Deploy", "Update", "Status", "Teardown")] [string] $Action = "Status",
    [string] $Profile = "saathi-aws",
    [string] $Region = "ap-southeast-2",
    [string] $StackName = "saathi-care-demo",
    [string] $SecretName = "saathi-care/demo",
    [string] $InstanceType = "t4g.small",
    [switch] $ConfirmTeardown
)
$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"   # the AWS CLI is Python: without this, build output containing a checkmark crashes it on a cp1252 console
$root = Split-Path -Parent $PSScriptRoot
$aws = (Get-Command aws -ErrorAction SilentlyContinue).Source
if (-not $aws) { $aws = "$env:LOCALAPPDATA\Programs\Amazon\AWSCLIV2\aws.exe" }
function A { & $aws @args --region $Region --profile $Profile; if ($LASTEXITCODE -ne 0) { throw "aws $($args[0]) $($args[1]) failed (exit $LASTEXITCODE)" } }

# ---- identity: print the ACCOUNT ONLY, never credentials ----------------------------------------------------------------
$acct = A sts get-caller-identity --query Account --output text
Write-Host "AWS account $acct, region $Region, profile $Profile"

function New-SourceTarball {
    $out = Join-Path $env:TEMP "saathi-source.tgz"
    if (Test-Path $out) { Remove-Item $out -Force }
    $items = @("app", "config", "prompts", "requirements.txt", "Dockerfile", "Dockerfile.frontend", ".dockerignore", "deploy",
               "data/programs.json", "data/members.json", "data/lab_packages.json",
               "frontend/index.html", "frontend/package.json", "frontend/package-lock.json", "frontend/tsconfig.json",
               "frontend/vite.config.ts", "frontend/src")
    & tar.exe -czf $out -C $root --exclude=__pycache__ --exclude=*.pyc @items
    if ($LASTEXITCODE -ne 0) { throw "tar failed" }
    # Guard: refuse to ship anything that looks like a secret or a database.
    $listing = & tar.exe -tzf $out
    $bad = $listing | Where-Object { $_ -match '(^|/)\.env($|\.)' -and $_ -notmatch '\.env\.example$' -or $_ -match '\.(db|db-shm|db-wal|log)$' }
    if ($bad) { throw "Refusing to upload: secrets/state found in tarball: $($bad -join ', ')" }
    Write-Host ("Source tarball: {0:N1} MB, {1} files, no .env / *.db / *.log" -f ((Get-Item $out).Length / 1MB), $listing.Count)
    return $out
}

function Get-StackOutput($key) { A cloudformation describe-stacks --stack-name $StackName --query "Stacks[0].Outputs[?OutputKey=='$key'].OutputValue" --output text }

# Probe helpers: an EXPECTED failure (e.g. "stack does not exist") writes to stderr, which Windows PowerShell 5.1 turns into a
# terminating error under $ErrorActionPreference = "Stop". Run those probes with "Continue" and judge by exit code only.
function Test-Aws {
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    try { & $aws @args --region $Region --profile $Profile *> $null; return ($LASTEXITCODE -eq 0) } finally { $ErrorActionPreference = $old }
}
function Get-AwsOrNull {
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    try { $o = & $aws @args --region $Region --profile $Profile 2>$null; if ($LASTEXITCODE -eq 0) { return $o } else { return $null } } finally { $ErrorActionPreference = $old }
}
function Stack-Exists { return (Test-Aws cloudformation describe-stacks --stack-name $StackName) }

switch ($Action) {
    "Status" {
        if (-not (Stack-Exists)) { Write-Host "Stack $StackName does not exist."; break }
        A cloudformation describe-stacks --stack-name $StackName --query "Stacks[0].[StackStatus]" --output text
        A cloudformation describe-stacks --stack-name $StackName --query "Stacks[0].Outputs[].[OutputKey,OutputValue]" --output text
    }

    "Deploy" {
        if (Stack-Exists) { throw "Stack $StackName already exists. Use -Action Update to ship new code." }

        # ---- 1. secret (created once; never overwritten here) -------------------------------------------------------------
        if (-not (Test-Aws secretsmanager describe-secret --secret-id $SecretName)) {
            $envFile = Join-Path $root ".env"
            if (-not (Test-Path $envFile)) { throw ".env not found at $envFile" }
            $vals = @{}
            Get-Content $envFile | ForEach-Object { if ($_ -match '^\s*([A-Z0-9_]+)\s*=\s*(.*)$') { $vals[$Matches[1]] = $Matches[2].Trim() } }
            $allow = "GEMINI_API_KEY", "OPENAI_API_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"   # NO Telegram / lab keys
            $secret = [ordered]@{}
            foreach ($k in $allow) { if ($vals[$k]) { $secret[$k] = $vals[$k] } }
            $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
            function New-Token { $b = New-Object byte[] 32; $rng.GetBytes($b); [Convert]::ToBase64String($b).TrimEnd('=').Replace('+','-').Replace('/','_') }
            $secret["COORDINATOR_TOKEN"] = New-Token
            $secret["ORIGIN_VERIFY"] = New-Token
            $tmp = New-TemporaryFile
            try {
                ($secret | ConvertTo-Json -Compress) | Set-Content -Path $tmp -Encoding ascii -NoNewline
                A secretsmanager create-secret --name $SecretName --description "Saathi Care demo: provider keys + generated tokens" --secret-string "file://$($tmp.FullName)" --query ARN --output text | Out-Null
            } finally { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
            Write-Host "Created secret '$SecretName' with keys: $($secret.Keys -join ', ')  (values not shown)"
        } else { Write-Host "Secret '$SecretName' already exists; leaving it unchanged." }
        $secretArn = A secretsmanager describe-secret --secret-id $SecretName --query ARN --output text

        # ---- 2. network inputs (existing default VPC; nothing created) ----------------------------------------------------
        $vpc = A ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query "Vpcs[0].VpcId" --output text
        $subnet = A ec2 describe-subnets --filters "Name=vpc-id,Values=$vpc" "Name=default-for-az,Values=true" --query "Subnets[0].SubnetId" --output text
        $pl = A ec2 describe-managed-prefix-lists --filters "Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing" --query "PrefixLists[0].PrefixListId" --output text

        # ---- 3. stack (billable resources are created here) ---------------------------------------------------------------
        $tgz = New-SourceTarball
        if (-not (Test-Aws cloudformation validate-template --template-body "file://$root\deploy\cloudformation.yaml")) { throw "Template validation failed" }
        A cloudformation create-stack --stack-name $StackName --template-body "file://$root\deploy\cloudformation.yaml" `
            --capabilities CAPABILITY_IAM --on-failure ROLLBACK `
            --parameters "ParameterKey=SecretArn,ParameterValue=$secretArn" "ParameterKey=VpcId,ParameterValue=$vpc" `
                         "ParameterKey=SubnetId,ParameterValue=$subnet" "ParameterKey=CloudFrontPrefixListId,ParameterValue=$pl" `
                         "ParameterKey=InstanceType,ParameterValue=$InstanceType" `
            --tags "Key=app,Value=saathi-care-demo" --output text | Out-Null
        Write-Host "Stack creation started."

        # ---- 4. upload the release as soon as the private bucket exists ---------------------------------------------------
        $bucket = $null
        for ($i = 0; $i -lt 60 -and -not $bucket; $i++) {
            $bucket = Get-AwsOrNull cloudformation describe-stack-resource --stack-name $StackName --logical-resource-id SourceBucket `
                --query "StackResourceDetail.PhysicalResourceId" --output text
            if (-not $bucket -or $bucket -eq "None") { $bucket = $null; Start-Sleep -Seconds 5 }
        }
        if (-not $bucket) { throw "Bucket was not created in time; check the stack events." }
        A s3 cp $tgz "s3://$bucket/releases/saathi-source.tgz" --only-show-errors
        Write-Host "Uploaded release to s3://$bucket/releases/saathi-source.tgz"

        Write-Host "Waiting for the stack (about 5-8 minutes: CloudFront is the slow part)..."
        A cloudformation wait stack-create-complete --stack-name $StackName
        Write-Host "Stack created. Site URL: $(Get-StackOutput SiteUrl)"
        Write-Host "The host now builds the images and starts the containers (about 5-10 more minutes)."
        Write-Host "Check progress with: .\deploy\deploy.ps1 -Action Status, then open the Site URL or curl <SiteUrl>/api/health."
    }

    "Update" {
        $tgz = New-SourceTarball
        $bucket = Get-StackOutput SourceBucketName
        $iid = Get-StackOutput InstanceId
        A s3 cp $tgz "s3://$bucket/releases/saathi-source.tgz" --only-show-errors
        $cmd = "aws s3 cp s3://$bucket/releases/saathi-source.tgz /opt/saathi/src.tgz --region $Region && rm -rf /opt/saathi/src && mkdir -p /opt/saathi/src && tar -xzf /opt/saathi/src.tgz -C /opt/saathi/src && bash /opt/saathi/src/deploy/host/run.sh"
        $pf = Join-Path $env:TEMP "saathi_ssm_update.json"   # a JSON file avoids shell-quoting problems entirely
        (@{ commands = @($cmd) } | ConvertTo-Json -Compress) | Set-Content -Path $pf -Encoding ascii
        try { $id = A ssm send-command --instance-ids $iid --document-name AWS-RunShellScript --parameters "file://$pf" --timeout-seconds 1800 --query Command.CommandId --output text }
        finally { Remove-Item $pf -Force -ErrorAction SilentlyContinue }
        Write-Host "SSM command $id sent; waiting..."
        A ssm wait command-executed --command-id $id --instance-id $iid
        A ssm get-command-invocation --command-id $id --instance-id $iid --query "[Status,StandardOutputContent]" --output text
    }

    "Teardown" {
        if (-not $ConfirmTeardown) { throw "Refusing to delete anything. Re-run with -ConfirmTeardown to delete stack $StackName (host, data volume, bucket, CloudFront)." }
        if (-not (Stack-Exists)) { Write-Host "Nothing to delete."; break }
        $bucket = Get-StackOutput SourceBucketName
        if ($bucket) { A s3 rm "s3://$bucket" --recursive --only-show-errors }   # bucket must be empty
        A cloudformation delete-stack --stack-name $StackName
        A cloudformation wait stack-delete-complete --stack-name $StackName
        Write-Host "Stack deleted. The secret '$SecretName' was NOT deleted (it is not part of the stack). Delete it separately if you want:"
        Write-Host "  aws secretsmanager delete-secret --secret-id $SecretName --recovery-window-in-days 7 --region $Region --profile $Profile"
    }
}
