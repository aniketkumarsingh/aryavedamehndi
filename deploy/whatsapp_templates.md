# WhatsApp templates to submit (MSG91 → WhatsApp → Templates)

WhatsApp only delivers templates Meta has approved. Create each one below
with **exactly this name** and language **English (en)**; the numbered
variables are filled in by `app/services/messaging.py` (`TEMPLATES`) in this
order. Utility templates are order/booking updates; Marketing templates
are only sent to customers who opted in, and end with an unsubscribe link.
Approval usually takes minutes to a day - email covers the gap.

| Name | Category | Body |
|---|---|---|
| `order_confirmed` | Utility | Hi {{1}}, your AryaVeda Mehndi order {{2}} is confirmed (₹{{3}}). We'll message you when it ships. |
| `order_shipped` | Utility | Hi {{1}}, your order {{2}} has shipped with {{3}}. Track it: {{4}} |
| `order_out_for_delivery` | Utility | Hi {{1}}, your order {{2}} is out for delivery today. {{3}} |
| `order_delivered` | Utility | Hi {{1}}, your order {{2}} has been delivered. We hope you love it! |
| `refund_processed` | Utility | Hi {{1}}, we've refunded ₹{{2}} for order {{3}}. Banks usually show it within 5-7 working days. |
| `booking_confirmed` | Utility | Hi {{1}}, your mehndi booking with {{2}} is confirmed for {{3}}. |
| `artist_en_route` | Utility | Hi {{1}}, {{2}} is on the way to you now. |
| `cart_reminder` | Marketing | Hi {{1}}, your mehndi picks are still in your cart: {{2}} — Not interested? Unsubscribe: {{3}} |
| `cart_reminder_coupon` | Marketing | Hi {{1}}, here's {{3}}% off your cart with code {{2}}, valid for 72 hours: {{4}} — Unsubscribe: {{5}} |
| `occasion_nudge` | Marketing | Hi {{1}}, {{2}} is coming up! Book {{3}} again before slots fill up: {{4}} — Unsubscribe: {{5}} |

After approval, set `MSG91_WHATSAPP_NUMBER` (the business number connected
in MSG91) in `deploy/.env`. Check the request format in
`messaging.deliver_whatsapp` against MSG91's current WhatsApp API docs with
the first live send; failures retry and show in Admin → Payments → jobs.
