import { defineTool } from "eve/tools";
import { always } from "eve/tools/approval";
import { z } from "zod";
import { CollectionProposal, makeActionKey } from "../../src/domain";

const Input = z.object({
  proposalId: z.string().min(1), tenantId: z.string().min(1), invoiceId: z.string().min(1),
  recipient: z.string().email(), subject: z.string().min(1), body: z.string().min(1),
  evidenceRefs: z.array(z.string().min(1)).min(1), proposalVersion: z.number().int().positive(),
});

export default defineTool({
  description: "Create a collection-email proposal. Always gated by human approval and no external side effect in this first slice.",
  inputSchema: Input,
  approval: always(),
  async execute(input) {
    return CollectionProposal.parse({ ...input, actionKey: makeActionKey(input.tenantId, input.invoiceId, input.proposalVersion), requiresApproval: true });
  },
});
