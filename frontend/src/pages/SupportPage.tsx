import { HeartHandshake, MessageCircle, Phone, ShieldCheck, UserCheck } from "lucide-react";
import { useApp } from "../app/context";
import { goto } from "../app/routes";
import { HandoffNotice } from "../components/booking/BookingFlow";
import { Button, Card, PageHeader } from "../components/ui";

const STEPS = [
  { icon: MessageCircle, t: "You ask Saathi", d: "Booking and wellness requests are handled automatically whenever they can be." },
  { icon: HeartHandshake, t: "A person steps in when needed", d: "If a booking can't be completed automatically (for example the lab system is unavailable) your request is sent to a care coordinator. Nothing is booked yet." },
  { icon: UserCheck, t: "A coordinator decides", d: "They approve (and will call you to arrange the test) or decline with a reason. Your screen updates by itself." },
];

export function SupportPage() {
  const { s, cfg } = useApp();
  const session = s.session;
  return (
    <div className="stack">
      <PageHeader eyebrow="Care team" title="Human support" subtitle="Saathi is an AI assistant. For anything it can't finish, trained people are in the loop." />

      {session && session.handoff.status !== "none" && <HandoffNotice handoff={session.handoff} booking={session.booking} />}
      {session && session.handoff.status === "none" && <Card className="flat"><div className="card-title"><ShieldCheck size={18} aria-hidden="true" />No coordinator request</div><p className="muted">You have no open request. If a booking can't be completed automatically it will appear here with its status.</p></Card>}
      {!session && <Card className="flat"><p className="muted">Start a session from the Overview to see the status of any coordinator request.</p></Card>}

      <section aria-label="How it works" className="grid-3">
        {STEPS.map((x, i) => { const I = x.icon; return (
          <Card key={x.t}><span className="qa-ic"><I size={20} aria-hidden="true" /></span><h3 style={{ margin: "12px 0 6px" }}>{i + 1}. {x.t}</h3><p className="muted">{x.d}</p></Card>); })}
      </section>

      <div className="grid-2">
        <Card>
          <div className="card-title"><Phone size={18} aria-hidden="true" />In an emergency</div>
          <p className="muted">If you or someone else is in danger or has severe symptoms (such as chest pain or trouble breathing), call <b>112</b> now. Don't wait for Saathi or a coordinator.</p>
        </Card>
        <Card>
          <div className="card-title"><MessageCircle size={18} aria-hidden="true" />Need something else?</div>
          <p className="muted">Ask Saathi in chat or by voice. If it can't help, it will tell you.</p>
          <div className="row-gap" style={{ marginTop: 12 }}><Button variant="primary" onClick={() => goto("chat")}>Open chat</Button><Button onClick={() => goto("voice")}>Talk to Mimi</Button></div>
        </Card>
      </div>

      {cfg?.coordinator_console_enabled && (
        <p className="help staff-link">Care-team staff: <a href="#/coordinator">open the coordinator console</a> (requires the coordinator token).</p>
      )}
    </div>
  );
}
