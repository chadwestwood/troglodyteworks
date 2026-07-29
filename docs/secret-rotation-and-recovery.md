# Secret Rotation and Recovery

**Owner:** Platform administrator  
**Applies to:** Railway production services and connected providers  
**Rule:** Never copy secret values into GitHub, Linear, documentation, chat, screenshots, logs, or support messages.

## Production inventory

Railway is the source of truth for application secret variables. The web and
worker services share database, Discord, and provider-encryption configuration.
The web service additionally holds OAuth credentials. Optional integrations add
their own server-side variables only when enabled.

Required names can be verified from inside the applicable Railway service
without printing their values:

```text
python scripts/verify_secret_inventory.py web
python scripts/verify_secret_inventory.py worker
```

The command reports variable names as configured or missing. It never prints a
value. A successful web check also proves secure cookies are enabled.

## Rotation order

Rotate one credential family at a time. Keep the prior value available until
the replacement has been verified, except when active compromise requires
immediate revocation.

1. Create the replacement at the provider or with an approved cryptographic
   generator.
2. Put the replacement directly into every Railway service that consumes it.
3. Redeploy those services and run the inventory check.
4. Exercise the smallest relevant production check:
   - Google: sign in and return to My Communities.
   - Discord OAuth: link an account and refresh managed servers.
   - Discord bot: confirm the worker connects and a read-only command replies.
   - Nitrado or another host: refresh services and read World status.
   - CurseForge: resolve one known mod without changing a World.
   - Railway provider token: read the managed-hosting prerequisite check.
5. Revoke the replaced provider credential.
6. Record only the credential family, date, operator, validation result, and
   revocation result. Do not record either value.

## Provider-encryption key rotation

`TWE_PROVIDER_SECRET_KEYS_JSON` is a versioned keyring and
`TWE_PROVIDER_SECRET_ACTIVE_KEY_VERSION` selects the key for new writes.

1. Add a new randomly generated 32-byte key under a new version name.
2. Deploy the complete keyring with the new version active.
3. Re-encrypt stored provider envelopes with the application rotation path.
4. Verify every provider connection before removing the old key.
5. Retire the old key only after no stored envelope references it.

Removing an old key too early makes existing encrypted provider credentials
unrecoverable.

## Recovery

- **Suspected exposure:** revoke first, replace in Railway, redeploy, validate,
  and review audit records. Removing a value from the current Git branch is not
  sufficient if it entered history.
- **Lost OAuth or bot credential:** issue a provider replacement, update every
  consumer together, then revoke the old credential.
- **Lost provider-encryption key:** restore the protected keyring backup. If no
  backup exists, connected provider credentials must be collected again from
  their owners.
- **Database credential loss:** rotate through Railway, update all dependent
  services, and verify migrations, readiness, web sign-in, and the Discord
  worker before revocation.

## Minimum deployment gate

Before production deployment:

1. `python -m unittest scripts.test_security_check scripts.test_verify_secret_inventory`
2. `python scripts/security_check.py --production-config`
3. `python -m pip_audit --requirement backend/trog/requirements.txt`
4. backend regression tests
5. GitHub Security checks are green

Confirmed findings are fixed or tracked before deployment. Credentials found
in a change are revoked and replaced; they are never allowlisted as test data.
