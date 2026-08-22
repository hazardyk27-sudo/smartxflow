# Resend + Supabase Auth Email Setup

SmartXFlow uses Supabase Auth for account confirmation and password recovery.
Resend is the SMTP delivery provider; application code does not store or use a
Resend API key for these messages.

## Current Resend domain

`smartxflow.com` has been added to the connected Resend account. Its status is
pending DNS verification. Add the exact DNS values shown in the Resend domain
screen before enabling email delivery:

| Purpose | Type | Host | Value |
| --- | --- | --- | --- |
| DKIM | TXT | `resend._domainkey` | Copy the current Resend-provided public key |
| SPF / return path | MX | `send` | Copy the current Resend-provided MX target and priority |
| SPF | TXT | `send` | Copy the current Resend-provided SPF value |

Do not replace the root-domain SPF record unless the DNS provider confirms the
existing record can be safely merged. Resend provides the current values in its
Domains screen; that screen is the source of truth if records ever rotate.

## Supabase Custom SMTP

After Resend marks the domain as verified, configure the Supabase project:

1. Open **Authentication → Emails → SMTP Settings**.
2. Enable **Custom SMTP**.
3. Set host to `smtp.resend.com`, port to `587`, username to `resend`, and use
   a newly-created Resend SMTP/API key as the password.
4. Set the sender to `SmartXFlow <no-reply@smartxflow.com>`.
5. Keep **Confirm email** enabled.
6. Save the settings, then send a test confirmation email.

The Resend key belongs only in Supabase's SMTP settings. Do not add it to
application source, a migration file, browser storage, or chat.

## Redirect URLs

Supabase Auth must allow both callback URLs:

- Development: `https://<current-Replit-development-domain>/auth/callback`
- Production (for a later rollout): `https://www.smartxflow.com/auth/callback`

Set the Site URL to the environment that is currently being tested. A production
rollout is intentionally not part of this setup task.

## Suggested Supabase email copy

### Confirm signup

**Subject:** Confirm your SmartXFlow account

**Body:**

> Welcome to SmartXFlow. Confirm your email address to activate your account.
>
> {{ .ConfirmationURL }}
>
> If you did not create this account, you can safely ignore this email.

### Reset password

**Subject:** Reset your SmartXFlow password

**Body:**

> We received a request to reset your SmartXFlow password.
>
> {{ .ConfirmationURL }}
>
> If you did not request a password reset, you can safely ignore this email.

## Delivery and troubleshooting

- Check **Resend → Logs** for accepted, delivered, bounced, or failed messages.
- Check **Supabase → Authentication → Logs** when a confirmation or recovery
  link is not generated.
- SmartXFlow limits confirmation re-sends and password reset requests to one
  request per email per 60 seconds.
- Password-reset requests always return a generic success response, so the app
  does not disclose whether an address has an account.
- Before a production rollout, test confirmation, re-send confirmation,
  password reset, expired link, and callback redirects with a dedicated test
  account.