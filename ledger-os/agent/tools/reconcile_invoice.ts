import { defineTool } from "eve/tools";
import { z } from "zod";
import { Invoice, Payment, reconcile } from "../../src/domain";

const Input = z.object({ invoice: Invoice, payments: z.array(Payment) });

export default defineTool({
  description: "Deterministically classify an invoice against tenant-scoped payments. Never sends or mutates anything.",
  inputSchema: Input,
  async execute({ invoice, payments }) {
    return { invoiceId: invoice.invoiceId, classification: reconcile(invoice, payments) };
  },
});
