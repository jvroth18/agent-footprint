# Security policy

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability or accidental
data exposure. Use GitHub's private vulnerability reporting for this
repository instead.

Include the affected version, reproduction steps, expected impact, and any
suggested mitigation. Please avoid attaching real scan output: it can contain
hostnames, filesystem paths, repository names, process commands, and scheduled
task details.

## Sensitive generated files

`scan.json` and `dashboard.html` are local diagnostic artifacts. Do not commit,
publish, or send them without carefully reviewing and redacting their contents.
