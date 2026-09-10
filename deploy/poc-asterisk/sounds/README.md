# Required POC prompts

Install these Asterisk prompt names in every codec you enable:

- `poc-menu`: “Hello, and thank you for calling HTIS support. Press 1 for OpenAI. Press 2 for Gemini Live. Press 3 for Google cascade. Press 4 to talk with Anurag Mehra.”
- `poc-invalid`: “That option is not valid.”
- `poc-noinput`: “I did not receive a selection.”
- `poc-unavailable`: “That AI option is unavailable right now. Please call again or press 4 on the main menu for Anurag.”
- `poc-goodbye`: “Thank you for calling HTIS support. Goodbye.”
- `poc-failure-goodbye`: “Sorry, we couldn't complete your request right now. Please try again later. Goodbye.”

Generate prompts from owned text or record them locally; do not commit third-party audio.

For the seeded Dograh workflows, upload these as the stable recording IDs
`poc-success-goodbye` and `poc-failure-goodbye`. The seed assigns them as audio
transition speech on every edge entering the matching End Node.
