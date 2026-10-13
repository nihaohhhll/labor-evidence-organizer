"""Services package.

Every rule that must hold regardless of caller lives in a service, never in a
route handler or inside the model being checked (docs/14). In particular the
"AI output may not overwrite a user's edit" constraint is enforced here, not
in the AI layer that produces the values.
"""
