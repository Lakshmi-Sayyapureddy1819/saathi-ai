// Mirrors app/api_schemas.py. The UI renders these typed fields; it never parses chat text.
export type BookingStage = "idle" | "choosing_package" | "choosing_slot" | "confirming";
export type MessageKind =
  | "answer" | "safety_notice" | "emergency" | "booking_confirmed" | "handoff" | "handoff_resolved";
export type Triage = "GREEN_NORMAL" | "YELLOW_WARNING" | "RED_CRISIS";

// Mirrors ReminderCallView in app/api_schemas.py.
export interface ReminderCallResult {
  outcome: "booked" | "declined" | "no_pending_checkup" | "unfinished";
  transcript: string[];
  booking_ids: string[];
  trace_id: string;
  simulated: boolean;
}

export interface PackageOption {
  package_id: string; name: string; price_inr: number; test_count: number;
  fasting_required: boolean; fasting_hours: number;
}
export interface DateOption { word: "today" | "tomorrow" | "day after tomorrow"; label: string; iso: string }
export interface BookingView {
  stage: BookingStage; package: PackageOption | null; options: PackageOption[];
  date_iso: string | null; date_label: string | null; slot: string | null; slots: string[]; dates: DateOption[];
}
export interface BookingConfirmation { booking_id: string; package_name: string; date: string; slot: string }
export interface EmergencyView { message: string; helplines: Record<string, string> }
export interface HandoffView { status: "none" | "pending" | "approved" | "rejected"; ticket_id: string | null; note: string }
export interface ComponentStatus { name: string; mode: "real" | "simulated" | "disabled"; detail: string }
export interface Readiness { environment: "development" | "production"; ready: boolean; components: ComponentStatus[]; problems: string[] }
export type GroundingModeName = "mode_a_rag" | "mode_b_facts";
export interface Citation { source_id: string; title: string; kind: "document" | "backend_fact"; cited: boolean }
export interface GroundingView {
  mode: "mode_a_rag" | "mode_b_facts"; retriever: string; search_queries: string[]; tools_called: string[];
  agent_steps: number; decided_by: "llm" | "deterministic";
}
export interface ChatMessage {
  id: number; role: "user" | "assistant" | "system"; kind: MessageKind; text: string; at: string;
  trace_id: string | null; emergency: EmergencyView | null; confirmation: BookingConfirmation | null;
  citations?: Citation[]; grounding?: GroundingView | null;
  // client-only: set on an optimistic user bubble while the request is in flight or after it failed
  clientState?: "sending" | "failed";
}
export interface BookingItem { booking_id: string; package_name: string; date: string; slot: string }
export interface Member { member_id: string; name: string; age: number; language_preference: string }
export interface SessionView {
  session_id: string; member: Member; status: "active" | "awaiting_coordinator"; triage_status: Triage;
  messages: ChatMessage[]; booking: BookingView; handoff: HandoffView; bookings: BookingItem[];
  grounding_mode?: GroundingModeName;
}
export interface SessionCreated { session_token: string; session: SessionView }
export interface ConfigView {
  llm_configured: boolean; coordinator_console_enabled: boolean; max_message_chars: number;
  grounding_mode?: "mode_a_rag" | "mode_b_facts"; retriever?: string;
}
export interface Program { doc_id: string; title: string; category: string }
export interface ApprovalItem {
  session_id: string; member_id: string; member_name: string; ticket_id: string | null;
  package_name: string | null; date: string | null; slot: string | null; requested_at: string;
}
