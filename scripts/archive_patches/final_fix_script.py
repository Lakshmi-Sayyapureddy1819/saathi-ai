import re

print("Applying final architect fixes...")

graph_path = "app/workflow/graph.py"
with open(graph_path, "r", encoding="utf-8") as f:
    graph_content = f.read()

# Make sure lab_triggers has all necessary keywords
if "'price'" not in graph_content:
    graph_content = graph_content.replace("'lp', 'screen'", "'lp', 'screen', 'price', \\"l' 'p'\\", 'zero', 'one', 'two'")

with open(graph_path, "w", encoding="utf-8") as f:
    f.write(graph_content)

print(f"Updated {graph_path}")
