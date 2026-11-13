# N8rForge

**Developed by NORmal8r**

N8rForge is an infrastructure and operations platform for authorized security-awareness exercises and controlled phishing simulations. It centralizes campaign planning, test infrastructure configuration, and engagement reporting in a terminal user interface (TUI).

## Features

- **Centralized Management:** SQLite database for campaigns, approved test participants, and engagement events.
- **Campaign Management:** Create, review, and manage authorized awareness campaigns.
- **Infrastructure Configuration:** Document and validate approved test environments.
- **Cloudflare Integration:** Optional DNS configuration support for domains you own or are explicitly authorized to administer.
- **Training Assets:** Generate clearly controlled awareness-training pages and campaign materials.
- **Privacy-Respecting Metrics:** Record events such as page visits and training-link clicks without collecting real passwords, authentication tokens, or session cookies.
- **Delivery Tools:** QR-code generation and optional Telegram notifications.
- **Interactive TUI:** Rich text formatting, progress indicators, and guided menus.

## Safety Boundaries

N8rForge is intended for authorized awareness training and defensive security testing.

- Use only domains, infrastructure, and participant lists for which you have explicit authorization.
- Do not collect, store, replay, or inject passwords, authentication tokens, or session cookies.
- Do not impersonate third-party services outside an approved and clearly controlled exercise.
- Do not use cloaking or evasion to bypass security controls.
- Provide appropriate notice, approvals, and a clear training/ debrief process.

## Requirements

- **OS:** Ubuntu 22.04+ / Debian 12+ (or another Linux distribution with `apt`)
- **Python:** 3.9+
- **Privileges:** Use the least privileges required; avoid running the application as root.
- **Optional API:** Cloudflare API Token restricted to the specific zone and DNS permissions required.
- **Optional:** Telegram Bot Token for notifications.

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/NORmal8r/N8rForge.git
   cd N8rForge
   ```

2. Create and activate a virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies:

   ```bash
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. Start the application:

   ```bash
   python n8rforge.py
   ```

Do not place API tokens directly in source code or commit them to Git. Store secrets in environment variables or a local `.env` file that is excluded from version control.

## Usage

The planned TUI is organized into nine modules:

1. **Dashboard** — Overview of campaign status and aggregate engagement metrics.
2. **Campaigns** — Create and manage approved awareness campaigns.
3. **Participants** — Import authorized test participants via paste or CSV.
4. **Infrastructure** — Review and configure approved test infrastructure.
5. **Training Assets** — Prepare controlled educational landing pages and materials.
6. **Delivery** — Generate QR codes and configure optional notifications.
7. **Events** — Review privacy-respecting campaign events and reports.
8. **Run Exercise** — Start or stop an approved training exercise.
9. **Settings** — Manage integrations and application settings.

## Project Status

This README describes the intended project scope. Individual modules may still be under development.

## Legal Disclaimer

This software is provided for authorized security-awareness training, defensive testing, and educational research only. You are responsible for obtaining all necessary permissions and complying with applicable laws and organizational policies. The author assumes no liability for misuse or damage arising from use of this software.

## Author

**NORmal8r**
