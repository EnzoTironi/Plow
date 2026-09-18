import { describe, expect, it } from "vitest";
import { Invoice, Payment, makeActionKey, reconcile } from "../src/domain";

const invoice = Invoice.parse({ tenantId: "tenant-a", invoiceId: "inv-1", customerId: "cust-1", invoiceNumber: "A-100", total: { minor: 10000, currency: "brl" }, dueDate: "2026-09-01", status: "open" });
const payment = (minor: number, tenantId = "tenant-a") => Payment.parse({ tenantId, paymentId: `pay-${minor}`, customerId: "cust-1", amount: { minor, currency: "BRL" }, valueDate: "2026-09-02" });

describe("invoice-to-cash kernel", () => {
  it("classifies exact payment as paid", () => expect(reconcile(invoice, [payment(10000)])).toBe("paid"));
  it("classifies partial payment without crossing tenants", () => expect(reconcile(invoice, [payment(5000), payment(10000, "tenant-b")])).toBe("partial"));
  it("stops on overpayment ambiguity", () => expect(reconcile(invoice, [payment(11000)])).toBe("ambiguous"));
  it("creates stable idempotency keys", () => expect(makeActionKey("tenant-a", "inv-1", 1)).toBe("collection-email:tenant-a:inv-1:v1"));
});
