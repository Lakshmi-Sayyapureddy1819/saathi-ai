// Mirrors app/api_schemas.py. The UI renders these typed fields; it never parses chat text.
export type BookingStage = "idle" | "choosing_package" | "choosing_slot" | "confirming";
export type MessageKind =
  | "answer" | "safety_notice" | "emergency" | "booking_confirmed" | "handoff" | "handoff_resolved";
export type Triage = "GREEN_NORMAL" | "YELLOW_WARNING" | "RED_CRISIS";

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
export interface ChatMessage {
  id: number; role: "user" | "assistant" | "system"; kind: MessageKind; text: string; at: string;
  trace_id: string | null; emergency: EmergencyView | null; confirmation: BookingConfirmation | null;
  // client-only: set on an optimistic user bubble while the request is in flight or after it failed
  clientState?: "sending" | "failed";
}
export interface BookingItem { booking_id: string; package_name: string; date: string; slot: string }
export interface Member { member_id: string; name: string; age: number; language_preference: string }
export interface SessionView {
  session_id: string; member: Member; status: "active" | "awaiting_coordinator"; triage_status: Triage;
  messages: ChatMessage[]; booking: BookingView; handoff: HandoffView; bookings: BookingItem[];
}
export interface SessionCreated { session_token: string; session: SessionView }
export interface ConfigView { llm_configured: boolean; coordinator_console_enabled: boolean; max_message_chars: number }
export interface Program { doc_id: string; title: string; category: string }
export interface ApprovalItem {
  session_id: string; member_id: string; member_name: string; ticket_id: string | null;
  package_name: string | null; date: string | null; slot: string | null; requested_at: string;
}
