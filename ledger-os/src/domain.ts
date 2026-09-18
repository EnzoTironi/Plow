import { z } from "zod";

export const Money = z.object({ minor: z.number().int(), currency: z.string().length(3).transform((value) => value.toUpperCase()) });
export type Money = z.infer<typeof Money>;

export const Invoice = z.object({ tenantId: z.string().min(1), invoiceId: z.string().min(1), customerId: z.string().min(1), invoiceNumber: z.string().min(1), total: Money, dueDate: z.string().date(), status: z.enum(["open", "paid", "partial", "disputed", "ambiguous"]) });
export type Invoice = z.infer<typeof Invoice>;

export const Payment = z.object({ tenantId: z.string().min(1), paymentId: z.string().min(1), customerId: z.string().min(1), amount: Money, valueDate: z.string().date() });
export type Payment = z.infer<typeof Payment>;

export const CollectionProposal = z.object({ proposalId: z.string().min(1), tenantId: z.string().min(1), invoiceId: z.string().min(1), recipient: z.string().email(), subject: z.string().min(1), body: z.string().min(1), evidenceRefs: z.array(z.string().min(1)).min(1), actionKey: z.string().min(1), requiresApproval: z.literal(true) });
export type CollectionProposal = z.infer<typeof CollectionProposal>;

export function reconcile(invoice: Invoice, payments: Payment[]): "paid" | "partial" | "open" | "ambiguous" {
  const relevant = payments.filter((p) => p.tenantId === invoice.tenantId && p.customerId === invoice.customerId && p.amount.currency === invoice.total.currency);
  const totalPaid = relevant.reduce((sum, payment) => sum + payment.amount.minor, 0);
  if (totalPaid === invoice.total.minor) return "paid";
  if (totalPaid > 0 && totalPaid < invoice.total.minor) return "partial";
  if (totalPaid > invoice.total.minor) return "ambiguous";
  return "open";
}

export function makeActionKey(tenantId: string, invoiceId: string, proposalVersion: number): string { return `collection-email:${tenantId}:${invoiceId}:v${proposalVersion}`; }
