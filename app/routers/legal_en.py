"""English versions of the legal documents (`/legal/<name>?lang=en`).

The Russian originals live in legal.py. These are *translations of the same
commitments*, not a second set of promises: when a clause changes there it
must change here, and `REVISION` is bumped for both. Stripe's reviewers and
the Estonian regulator do not read Russian, which is the whole reason this
file exists.

Like the originals, these are templates: a lawyer in the company's
jurisdiction has to read them before the service sells anything.
"""

from __future__ import annotations

import html

from fastapi import Response

from app.config import get_settings


def _prices_en() -> tuple[str, str]:
    from app.services import payment_service
    from app.services.payments import money

    methods = payment_service.platform_methods()
    if not methods:
        return ("The price of launching a bot is shown on the publish button.", "")
    launch = ", ".join(sorted({money(m.price_minor, m.currency) for m in methods}))
    periodic = sorted({money(m.renewal_price_minor, m.currency) for m in methods if m.renewal_price_minor > 0})
    days = get_settings().renewal_period_days
    return (
        f"Launching one bot: {launch} (one-off).",
        f"Running a launched bot: {', '.join(periodic)} per {days} days." if periodic else "",
    )


def _agent_clause(settings, what: str) -> str:
    if not settings.agent_ready:
        return ""
    return (
        f"<li>{what} is carried out by the payment agent {html.escape(settings.agent_name)} "
        f"({html.escape(settings.agent_id)}) on behalf of and on the instructions of the Provider. "
        "The agent is not a party to the contract: the obligations towards the User are the Provider's.</li>"
    )


def gdpr_section(settings) -> str:
    """The GDPR block of the privacy policy (English)."""
    name = html.escape(settings.legal_name)
    location = (
        f"<li>The servers of the service are located in: {html.escape(settings.data_location)}. "
        "This country may be outside the European Economic Area.</li>"
        if settings.data_location
        else ""
    )
    return f"""
<h2>7. Your rights (GDPR and similar laws)</h2>
<ul>
  <li>The controller of your account data is {name}. For the data of a bot's buyers the controller is the
      bot owner, and {name} acts as processor (see
      <a href="/legal/data-processing?lang=en">Data Processing Terms</a>).</li>
  <li>Legal bases: performance of the contract (Art. 6(1)(b) GDPR) — to run the service; legitimate interests
      (Art. 6(1)(f)) — security and fraud prevention; legal obligation (Art. 6(1)(c)) — accounting and tax records.</li>
  <li>Retention: account data while the account exists and up to 30 days after deletion; accounting records for
      the period required by the applicable law.</li>
  <li>You may ask for access to your data, its correction, erasure, restriction of processing, portability, and
      you may object to processing. Write to the contacts below; we answer within one month.</li>
  <li>You may complain to the supervisory authority. In Estonia it is the Data Protection Inspectorate
      (Andmekaitse Inspektsioon, aki.ee).</li>
  {location}
</ul>
"""


def _offer(s) -> tuple[str, str]:
    launch, periodic = _prices_en()
    site = html.escape(s.public_base_url.rstrip("/"))
    name = html.escape(s.legal_name)
    agent = _agent_clause(s, "Receiving payments from the User")
    agent_note = (
        "<li>On a bank statement the payment may appear under the name of the payment agent.</li>"
        if s.agent_ready
        else ""
    )
    return "Public Offer (Terms of Service)", f"""
<p>{name} (the "Provider") offers any person with legal capacity (the "User") to enter into a contract for
the use of the Telegram bot builder service available at {site}, on the terms below.</p>

<h2>1. Subject</h2>
<ul>
  <li>The Provider gives access to a service that lets the User build the scenario of a Telegram bot and run it
      on the Provider's servers.</li>
  <li>Registration, building, storing, editing and previewing a scenario are free and not limited in time.</li>
  <li>Launching the bot in Telegram and keeping it running are paid.</li>
</ul>

<h2>2. Price and payment</h2>
<ul>
  <li>{html.escape(launch)}</li>
  {f"<li>{html.escape(periodic)}</li>" if periodic else ""}
  <li>The price is shown to the User before any charge, on the bot's publish screen.</li>
  <li>Payment is made through the payment services shown on the payment page. The Provider does not store the
      User's card data.</li>
  {agent}
  {agent_note}
  <li>If a period of operation is not paid, the bot keeps running for {s.renewal_grace_days} more days and is then
      taken off the air. The scenario, settings and data are kept and remain available to the User.</li>
</ul>

<h2>3. Money of the User's buyers</h2>
<ul>
  <li>Payments that the User's bot receives from its buyers go directly to the User's own account with the User's
      payment provider. The Provider is not a party to these settlements and does not receive or hold the buyers'
      funds.</li>
  <li>The keys to the User's payment provider are stored encrypted and used only to issue invoices from the
      User's bot.</li>
  <li>The User alone is responsible for the goods or services sold, their delivery, refunds, taxes and compliance
      with consumer protection law.</li>
</ul>

<h2>4. What the User must not sell through the service</h2>
<ul>
  <li>goods and services whose circulation is restricted or prohibited by law;</li>
  <li>material that infringes the rights of third parties, including copyright;</li>
  <li>mailings to people who have not subscribed to them.</li>
</ul>
<p>See also the <a href="/legal/acceptable-use?lang=en">Acceptable Use Policy</a>. On a violation the Provider may
take the bot off the air, notifying the User.</p>

<h2>5. Refunds</h2>
<ul>
  <li>If, through the Provider's fault, the service did not keep the bot running during a paid period, the payment
      for the unused part is refunded on the User's request.</li>
  <li>Send the request to the contacts below; it is reviewed within 10 business days. Details:
      <a href="/legal/refunds?lang=en">Refund Policy</a>.</li>
</ul>

<h2>6. Limitation of liability</h2>
<ul>
  <li>The service is provided "as is". The Provider does not guarantee that the User's bot will bring any income.</li>
  <li>The Provider is not responsible for outages of Telegram, payment systems and other third-party services, or
      for the content of the User's bot.</li>
  <li>The Provider's liability is limited to the amount the User paid for the current period of operation.</li>
</ul>

<h2>7. Related documents</h2>
<p>The contract includes the <a href="/legal/privacy?lang=en">Privacy Policy</a>,
<a href="/legal/refunds?lang=en">Refund Policy</a>,
<a href="/legal/acceptable-use?lang=en">Acceptable Use Policy</a> and
<a href="/legal/data-processing?lang=en">Data Processing Terms</a>. The service is an independent product and is not
affiliated with Telegram Messenger Inc.</p>

<h2>8. Acceptance and changes</h2>
<ul>
  <li>The contract is concluded when the User registers in the service.</li>
  <li>The Provider may change these terms by publishing a new revision at this address. Changes do not apply to a
      period already paid for.</li>
</ul>
"""


def _privacy(s) -> tuple[str, str]:
    name = html.escape(s.legal_name)
    agent = _agent_clause(s, "Payment data (amount, time, and the payer's e-mail if the payment system asks for it) is processed on payment")
    return "Privacy Policy", f"""
<p>This policy describes what data {name} collects when the service is used, why, and for how long it is kept.</p>

<h2>1. Data of service users</h2>
<ul>
  <li>When signing in with Telegram the service receives from Telegram an identifier, a name and, if public, a
      username. The service does not ask for or store a password.</li>
  <li>Bot scenarios, settings and uploaded files are kept until the User deletes them or the account.</li>
  <li>Keys to the User's payment provider are stored encrypted and are not shown again after saving.</li>
  <li>Messages you write to support through the service's bot are received by the Provider: they are needed to
      reply and are kept in the Telegram support chat until deleted.</li>
</ul>

<h2>2. Data of a bot's buyers</h2>
<ul>
  <li>The service stores the identifier, Telegram username and order history of those who talked to the bot, so
      that the bot can hand over what was paid for and the owner can see their sales.</li>
  <li>The service does not receive or store buyers' card data: payment takes place on the payment system's side.</li>
  <li>The bot owner is the controller of their buyers' data; the service processes it on their instructions and
      only to run the bot.</li>
</ul>

<h2>3. Disclosure to third parties</h2>
<ul>
  <li>Data goes only to services without which the bot cannot work: Telegram and the payment system chosen by
      the User.</li>
  <li>Data is not sold and not used for advertising.</li>
  {agent}
</ul>

<h2>4. Storage and protection</h2>
<ul>
  <li>Data is stored on servers to which only the Provider has access.</li>
  <li>Payment keys and bot tokens are stored encrypted.</li>
  <li>A copy of the database is made before service updates; copies are kept on the Provider's servers with
      restricted access.</li>
</ul>

<h2>5. Cookies and analytics</h2>
<ul>
  <li>The service uses no advertising or analytics trackers. See
      <a href="/legal/cookies?lang=en">Cookies and Local Storage</a>.</li>
</ul>

<h2>6. Deletion</h2>
<ul>
  <li>The User can delete a bot with its scenario and files at any time from the account.</li>
  <li>A request to delete the account and all related data is sent to the contacts below and fulfilled within
      30 days.</li>
  <li>A bot's buyer can opt out of mailings with the /stop command and from a subscription with /cancel in the
      bot itself.</li>
</ul>
{gdpr_section(s)}
"""


def _refunds(s) -> tuple[str, str]:
    name = html.escape(s.legal_name)
    launch, periodic = _prices_en()
    agent = _agent_clause(s, "Refunding money to the User")
    return "Refund Policy", f"""
<p>This page explains when and how {name} (the "Provider") refunds money for the service. It supplements the
<a href="/legal/offer?lang=en">Public Offer</a>.</p>

<h2>1. What can be refunded by the Provider</h2>
<ul>
  <li>If the bot did not run through the Provider's fault during a paid period, the payment for the unused part of
      the period is refunded.</li>
  <li>If a payment was charged twice or by mistake, the extra charge is refunded in full.</li>
  <li>If a launch was paid for but the bot was not launched through the Provider's fault, the launch fee is
      refunded.</li>
</ul>
<p>{html.escape(launch)} {html.escape(periodic)}</p>

<h2>2. When no refund is made</h2>
<ul>
  <li>If the bot does not work because of the User's actions: the token was revoked at @BotFather, the Telegram
      bot itself was deleted or blocked, the scenario was built incorrectly.</li>
  <li>If the bot was taken off the air for violating the
      <a href="/legal/acceptable-use?lang=en">Acceptable Use Policy</a>.</li>
  <li>For a period the bot has already run.</li>
  <li>If the failure is in Telegram or in a payment system the Provider does not control.</li>
</ul>

<h2>3. How to ask for a refund</h2>
<ul>
  <li>Write to the contacts below: say which bot and which payment, and what exactly did not work.</li>
  <li>We answer within 10 business days. Money is returned the way it was paid and in the same currency.</li>
  <li>The time it takes to arrive depends on the bank or payment system.</li>
  {agent}
</ul>

<h2>4. Refunds to buyers of your bots</h2>
<ul>
  <li>The Provider does not receive buyers' money and cannot refund it: it went to the bot owner's account. A buyer
      addresses refund questions to the bot owner.</li>
  <li>The owner makes the refund in their payment provider's account and marks the order as refunded in the
      builder — the bot tells the buyer and closes access if any was given.</li>
</ul>
"""


def _acceptable_use(s) -> tuple[str, str]:
    name = html.escape(s.legal_name)
    return "Acceptable Use Policy", f"""
<p>These rules apply to everyone who builds and launches bots in the service of {name}. They supplement the
<a href="/legal/offer?lang=en">Public Offer</a>.</p>

<h2>1. What is not allowed</h2>
<ul>
  <li>Selling or distributing what the law forbids in the bot owner's country or the buyer's: narcotics, weapons,
      forged documents, stolen data and the like.</li>
  <li>Deceiving buyers: taking money for what will not be delivered, imitating another shop, bank or service,
      collecting passwords, codes or card data.</li>
  <li>Distributing malware, phishing links, or material that infringes the rights of others.</li>
  <li>Publishing sexual material involving minors, calls to violence or extremism.</li>
  <li>Sending messages to people who have not subscribed, or breaking Telegram's own rules.</li>
  <li>Disrupting the service: overloading it with requests, looking for or exploiting vulnerabilities, bypassing
      limits.</li>
</ul>

<h2>2. What the Provider does about a violation</h2>
<ul>
  <li>May take a bot off the air without prior notice if the violation is obvious or puts buyers at risk.</li>
  <li>Otherwise first writes to the owner at the contacts they left and gives a reasonable time to fix it.</li>
  <li>For repeated or serious violations closes the account. Payment for the period in which the violation took
      place is not refunded.</li>
  <li>On a lawful request of a competent authority, discloses data to the extent the law requires.</li>
</ul>

<h2>3. How to report abuse</h2>
<p>If you come across a bot that breaks these rules, write to the contacts below with the bot's Telegram name and a
description of what happened. We review every report and reply.</p>

<h2>4. Responsibility of the bot owner</h2>
<p>The bot's owner is responsible for the bot's content, the goods and services it sells, and for compliance with tax
and consumer law. The Provider supplies a tool and does not review bots in advance.</p>
"""


def _data_processing(s) -> tuple[str, str]:
    name = html.escape(s.legal_name)
    agent = _agent_clause(s, "Receiving bot owners' payments for launching and running the service")
    return "Data Processing Terms for Bot Owners", f"""
<p>This document is for bot owners. It explains who is responsible for what when a bot collects data about your
buyers. It supplements the <a href="/legal/privacy?lang=en">Privacy Policy</a>.</p>

<h2>1. Roles</h2>
<ul>
  <li>The bot owner decides why and which buyer data the bot collects and is the controller of that data.</li>
  <li>{name} (the "Provider") processes it on the owner's instructions and only to make the bot work.</li>
</ul>

<h2>2. Data processed</h2>
<ul>
  <li>Telegram user identifier and chat identifier;</li>
  <li>name and Telegram username, if Telegram supplies them;</li>
  <li>order history: item, amount, payment and delivery status, time;</li>
  <li>marks of subscription to mailings and to paid access;</li>
  <li>answers to polls, if the owner uses them.</li>
</ul>
<p>The Provider does not receive card data: payment takes place on the side of the owner's payment system.</p>

<h2>3. Purposes and retention</h2>
<ul>
  <li>Purpose: delivering what was paid for, keeping the owner's sales log, mailings and subscription reminders.</li>
  <li>Data is kept while the bot exists. When a bot is deleted, the orders and buyers linked to it are deleted.</li>
</ul>

<h2>4. Who else receives the data</h2>
<ul>
  <li>Telegram — as the platform the bot runs on.</li>
  <li>The payment system chosen by the bot owner — for the payment data.</li>
  <li>The hosting provider whose servers the service runs on.</li>
  {agent}
</ul>
<p>There are no other recipients; data is not sold or used for advertising.</p>

<h2>5. Security measures</h2>
<ul>
  <li>Bot tokens and payment-system keys are stored encrypted.</li>
  <li>Access to an account is only through Telegram sign-in; signing out closes all issued sessions.</li>
  <li>Access to servers and the database is restricted to the Provider.</li>
</ul>

<h2>6. What the bot owner must do</h2>
<ul>
  <li>Have a lawful basis for processing buyers' data and tell them why it is collected.</li>
  <li>Not send messages to those who opted out: the bot understands /stop and excludes such people from mailings.</li>
  <li>Answer buyers' requests about access, correction and deletion of their data; the Provider helps technically.</li>
  <li>Not pass the Provider data that is not needed for the bot to work.</li>
</ul>

<h2>7. Deletion and breaches</h2>
<ul>
  <li>The owner can delete the bot and its data at any time from the account, or ask for the account to be deleted
      at the contacts below.</li>
  <li>If the Provider learns of a data breach, it notifies the owners of the affected bots without undue delay.</li>
</ul>
"""


def _cookies(_s) -> tuple[str, str]:
    return "Cookies and Local Storage", """
<p>In short: the site does not track you and shows no advertising.</p>

<h2>1. What we store in your browser</h2>
<ul>
  <li><strong>bf_session_token</strong> — the sign-in token, so you do not have to sign in on every visit. It appears
      after signing in with Telegram and is erased by the "Log out" button. Valid for 30 days.</li>
  <li><strong>bf_theme</strong> — the theme you chose (light, dark, or system).</li>
  <li><strong>bf_panel_offset</strong> — where you left the block editing window, if you dragged it.</li>
</ul>
<p>All of it lives in your browser's localStorage and is sent nowhere except the sign-in token, which goes to our
server so it knows who you are. The builder cannot work without it.</p>

<h2>2. What we do not do</h2>
<ul>
  <li>We use no advertising or analytics counters or pixels.</li>
  <li>We set no cookies of our own for tracking or advertising.</li>
  <li>We do not pass data about your actions on the site to third parties.</li>
</ul>

<h2>3. Third-party services on the page</h2>
<ul>
  <li>The Telegram sign-in button and script load from telegram.org. Telegram may use its own cookies when you
      sign in; that happens on Telegram's side and is described in its policy.</li>
  <li>Payment pages open at the chosen payment system and follow its rules.</li>
</ul>

<h2>4. How to remove it all</h2>
<p>Press "Log out" in the builder or clear the site's data in your browser settings.</p>
"""


BODIES = {
    "offer": _offer,
    "privacy": _privacy,
    "refunds": _refunds,
    "acceptable-use": _acceptable_use,
    "data-processing": _data_processing,
    "cookies": _cookies,
}


def render(slug: str) -> Response:
    from app.routers.legal import _page

    title, body = BODIES[slug](get_settings())
    return _page(title, body, "en")


def render_index() -> Response:
    from app.routers.legal import TITLES_EN, _page

    items = "".join(
        f'<li><a href="/legal/{slug}?lang=en">{html.escape(title)}</a></li>' for slug, title in TITLES_EN.items()
    )
    return _page("Documents", f"<ul>{items}</ul>", "en")
