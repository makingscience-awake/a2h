/**
 * A2H (Agent-to-Human) Protocol TypeScript Definitions
 */

export type PID = string; // format: "namespace/name"

export enum ResponseType {
    CHOICE = "choice",
    APPROVAL = "approval",
    TEXT = "text",
    NUMBER = "number",
    CONFIRM = "confirm",
    FORM = "form"
}

export enum Status {
    PENDING = "pending",
    DELIVERED = "delivered",
    ANSWERED = "answered",
    AUTO_DELEGATED = "auto_delegated",
    ESCALATED = "escalated",
    TIMEOUT = "timeout",
    CANCELLED = "cancelled",
    FAILED = "failed"
}

export interface Option {
    value: string;
    label: string;
}

export interface EscalationLevel {
    target: PID;
    timeout_minutes: number;
    priority_override?: string;
}

export interface EscalationChain {
    levels: EscalationLevel[];
}

export interface Interaction {
    id: string;
    to_name: PID;
    from_name: PID;
    question: string;
    response_type: ResponseType;
    options?: Option[];
    context?: Record<string, any>;
    priority: "low" | "normal" | "high" | "critical";
    deadline?: string; // ISO8601 duration or timestamp
    escalation?: EscalationChain;
    status: Status;
    created_at: string;
    updated_at: string;
    response?: any;
}

export interface HumanResponse {
    value: any;
    text?: string;
}
