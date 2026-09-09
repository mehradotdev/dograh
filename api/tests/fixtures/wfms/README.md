# WFMS discovery fixtures

These sanitized fixtures preserve the response topology observed from the dev
WFMS API on 2026-09-09. Names, phone numbers, email addresses, titles, and dates
are synthetic. The adapter tests also encode the observed defect where a bogus
ticket-number summary can return rows for request 19.

The successful CreateTicket shape was verified with an explicitly authorized
unregistered external-caller request. Its fixture is sanitized; the validation-only
response is retained as the failure shape.
