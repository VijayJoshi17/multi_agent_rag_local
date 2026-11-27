# Information Security Policy

This policy applies to every employee, contractor and intern at Larkspur Robotics. Questions go to the Security team in the #sec-help channel.

## Accounts and passwords

- Passwords must be at least 16 characters long. Passphrases are encouraged.
- Multi-factor authentication is mandatory for every company account. Hardware security keys (YubiKey) are required for anyone with production access; authenticator apps are acceptable for everyone else. SMS codes are not permitted.
- Passwords must be stored in the company 1Password vault. Sharing credentials over chat or email is forbidden.

## Devices

- Laptops must have full-disk encryption enabled and lock automatically after 5 minutes of inactivity.
- Operating system security updates must be installed within 14 days of release.
- Personal devices may access email and chat only through the managed mobile app; they may never access source code or production systems.

## Access to production systems

Production access is granted through just-in-time requests in the Access portal and expires after 8 hours. Access requests must reference a ticket. All production sessions are recorded.

## Secrets and keys

API keys and service credentials must be stored in the secrets manager, never in source code. Keys must be rotated at least every 90 days, and immediately when someone with access leaves the company.

## Reporting incidents

Suspected security incidents, phishing emails, and lost or stolen devices must be reported within 24 hours by emailing security@larkspur.example or posting in #sec-help. Reporting a mistake early is never punished.

## Data classification

Data is classified as Public, Internal, Confidential or Restricted. Customer fleet telemetry is Confidential. Customer contracts and employee personal data are Restricted and may only be stored in approved systems.
