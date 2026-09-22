# Zoen

Zoen is one assistant for one owner. The owner texts it. Zoen answers on the same line the text arrived on.

## Language

**Owner**:
The person bound to this Zoen by the phone that activated it.
_Avoid_: user, account, customer

**Line**:
A channel the owner texts. iMessage is the Plow phone line. WhatsApp is Zoen's line, on the same owner.
_Avoid_: channel, platform, transport

**Binding**:
The attachment of the WhatsApp line to the owner Plow already identified.
_Avoid_: account link, login

**Burst**:
Consecutive messages from one speaker that count as one request.
_Avoid_: batch, queue, thread

**Bubble**:
One WhatsApp message the owner can point at.
_Avoid_: wamid, quote, reply target

**Persona**:
Zoen's own half of the identity. The shared half belongs to every Plow agent.
_Avoid_: soul, prompt, voice file

**Connector**:
An outside service the owner has granted, or can grant, inside a private conversation with Zoen. Google is Zoen's own grant. Slack is Plow's grant. Every other connector is a Hermes catalog grant.
_Avoid_: integration, connection, account

**Playbook**:
A Zoen workflow a turn runs for the owner.
_Avoid_: skill, script, recipe

**Kit**:
The reusable process skills that ship with Zoen, kept apart from playbooks.
_Avoid_: principles, framework, agent kit
