"""Shared Gmail email normalization and cleaning utilities."""

from __future__ import annotations

import base64
import html
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TypeAlias, cast

from bs4 import BeautifulSoup

from ...logging_config import logger
from ...utils.timezones import convert_to_user_timezone

GmailPayload: TypeAlias = Mapping[str, object]


class EmailTextCleaner:
    """Clean and extract readable text from Gmail API email responses."""

    def __init__(self, max_url_length: int = 60) -> None:
        self.max_url_length: int = max_url_length
        self.remove_elements: list[str] = [
            "style",
            "script",
            "meta",
            "link",
            "title",
            "head",
            "noscript",
            "iframe",
            "embed",
            "object",
            "img",
        ]
        self.noise_elements: list[str] = [
            "footer",
            "header",
            ".footer",
            ".header",
            '[class*="footer"]',
            '[class*="header"]',
            '[class*="tracking"]',
            '[class*="pixel"]',
            '[style*="display:none"]',
            '[style*="display: none"]',
        ]

    # Public API
    # Extract and clean email content from Gmail API message payload
    def clean_email_content(self, message: GmailPayload) -> str:
        """Return cleaned plain-text representation of a Gmail message."""

        html_content = self._extract_html_body(message)
        text_content = self._extract_plain_body(message)

        if html_content:
            return self.clean_html_email(html_content)
        if text_content:
            return self.post_process_text(text_content)
        return ""

    # Clean HTML email content by removing unwanted elements and extracting text
    def clean_html_email(self, html_content: str) -> str:
        try:
            soup = BeautifulSoup(html_content, "html.parser")

            for element_type in self.remove_elements:
                for element in soup.find_all(element_type):
                    _ = element.decompose()

            for selector in self.noise_elements:
                try:
                    for element in soup.select(selector):
                        _ = element.decompose()
                except Exception as exc:  # pragma: no cover - defensive
                    logger.debug(
                        "Failed to remove element via selector",
                        extra={"selector": selector, "error": str(exc)},
                    )

            for link in soup.find_all("a"):
                raw_href = link.get("href", "")
                href = raw_href if isinstance(raw_href, str) else ""
                text = link.get_text(strip=True)

                if href:
                    display_url = self.truncate_url(href)

                    if text and text != href and not self.is_url_like(text):
                        _ = link.replace_with(f"{text} ({display_url})")
                    elif text and text != href:
                        _ = link.replace_with(f"[Link: {display_url}]")
                    else:
                        _ = link.replace_with(f"[Link: {display_url}]")

            text = soup.get_text(separator="\n", strip=True)
            return self.post_process_text(text)

        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Error cleaning HTML email", extra={"error": str(exc)})
            return self.fallback_text_extraction(html_content)

    def truncate_url(self, url: str) -> str:
        if not url or len(url) <= self.max_url_length:
            return url

        url = self.remove_tracking_params(url)
        if len(url) <= self.max_url_length:
            return url
        return f"{url[: self.max_url_length]}..."

    def remove_tracking_params(self, url: str) -> str:
        try:
            from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

            parsed = urlparse(url)
            if not parsed.query:
                return url

            tracking_params = {
                "utm_source",
                "utm_medium",
                "utm_campaign",
                "gclid",
                "fbclid",
                "ref",
                "trk",
            }

            query_params = parse_qs(parsed.query, keep_blank_values=False)
            cleaned_params = {
                key: value
                for key, value in query_params.items()
                if key.lower() not in tracking_params
            }

            new_query = urlencode(cleaned_params, doseq=True)
            new_parsed = parsed._replace(query=new_query)
            return urlunparse(new_parsed)

        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(
                "Failed to strip tracking params",
                extra={"error": str(exc), "url": url},
            )
            return url

    def is_url_like(self, text: str) -> bool:
        if not text:
            return False
        lowered = text.lower()
        if lowered.startswith(("http://", "https://", "www.", "ftp://")):
            return True
        return "." in lowered and " " not in lowered and len(lowered.split(".")) >= 2

    def post_process_text(self, text: str) -> str:
        text = html.unescape(text)
        text = re.sub(r"\n\s*\n\s*\n", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n ", "\n", text)

        noise_patterns = [
            r"View this email in your browser.*?\n",
            r"If you can't see this email.*?\n",
            r"This is a system-generated email.*?\n",
            r"Please do not reply to this email.*?\n",
            r"Unsubscribe.*?preferences.*?\n",
            r"© \d{4}.*?All rights reserved.*?\n",
            r"\[Image:.*?\]",
            r"\[Image\]",
            r"<image>.*?</image>",
            r"\(image\)",
            r"\(Image\)",
            r"Image: .*?\n",
            r"Alt text: .*?\n",
        ]

        for pattern in noise_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()
        return text

    def fallback_text_extraction(self, html_content: str) -> str:
        stripped = re.sub(r"<[^>]+>", " ", html_content)
        stripped = re.sub(r"\s+", " ", stripped)
        return self.post_process_text(stripped)

    def _extract_html_body(self, message: GmailPayload) -> str | None:
        payload = message.get("payload")
        payload_map = _as_string_mapping(payload)
        if payload_map is not None:
            payload = payload_map
            parts = payload.get("parts")
            if isinstance(parts, list):
                for raw_part in cast(list[object], parts):
                    part = _as_string_mapping(raw_part)
                    if part is None:
                        continue
                    mime_type = part.get("mimeType") or ""
                    if isinstance(mime_type, str) and mime_type.lower() == "text/html":
                        body = part.get("body")
                        body_map = _as_string_mapping(body)
                        if body_map is not None:
                            data = body_map.get("data")
                            if isinstance(data, str):
                                try:
                                    return base64.urlsafe_b64decode(data).decode(
                                        "utf-8", errors="replace"
                                    )
                                except Exception:
                                    continue
        html_body = message.get("htmlBody")
        return html_body if isinstance(html_body, str) else None

    def _extract_plain_body(self, message: GmailPayload) -> str | None:
        payload = message.get("payload")
        payload_map = _as_string_mapping(payload)
        if payload_map is not None:
            payload = payload_map
            body = payload.get("body")
            body_map = _as_string_mapping(body)
            if body_map is not None:
                body = body_map
                data = body.get("data")
                if isinstance(data, str):
                    try:
                        return base64.urlsafe_b64decode(data).decode(
                            "utf-8", errors="replace"
                        )
                    except Exception:
                        pass
        text_body = message.get("textBody")
        return text_body if isinstance(text_body, str) else None

    def extract_attachment_info(
        self, attachments: Iterable[object] | None
    ) -> tuple[bool, int, list[str]]:
        filenames: list[str] = []
        count = 0
        for item in attachments or []:
            item_map = _as_string_mapping(item)
            if item_map is not None:
                item = item_map
                filename = item.get("filename") or item.get("name")
                if filename:
                    filenames.append(str(filename))
                    count += 1
        return bool(count), count, filenames


@dataclass(frozen=True)
class ProcessedEmail:
    """Normalized Gmail message representation."""

    id: str
    thread_id: str | None
    query: str
    subject: str
    sender: str
    recipient: str
    timestamp: datetime
    label_ids: list[str]
    clean_text: str
    has_attachments: bool
    attachment_count: int
    attachment_filenames: list[str]


# ----------------------------------------------------------------------
# Helpers shared across modules
# ----------------------------------------------------------------------


# Parse Gmail timestamp string into timezone-aware datetime object
def parse_gmail_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None

    try:
        normalized = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
        dt = datetime.fromisoformat(normalized)
        return convert_to_user_timezone(dt)
    except ValueError:
        return None


# Convert raw Gmail API message into a clean ProcessedEmail object
def build_processed_email(
    message: GmailPayload,
    *,
    query: str,
    cleaner: EmailTextCleaner | None = None,
) -> ProcessedEmail | None:
    message_id = _string_value(message.get("messageId") or message.get("id"))
    if not message_id:
        logger.warning("Skipping email with missing message ID")
        return None

    cleaner = cleaner or EmailTextCleaner()

    timestamp = parse_gmail_timestamp(_optional_string(message.get("messageTimestamp")))
    if not timestamp:
        logger.warning(
            "Email missing timestamp; using current time",
            extra={"message_id": message_id},
        )
        timestamp = convert_to_user_timezone(datetime.now(timezone.utc))

    try:
        clean_text = cleaner.clean_email_content(message)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(
            "Failed to clean email content",
            extra={"message_id": message_id, "error": str(exc)},
        )
        clean_text = "Error processing email content"

    attachments = message.get("attachmentList")
    has_attachments, attachment_count, attachment_filenames = (
        cleaner.extract_attachment_info(
            attachments if isinstance(attachments, Iterable) else None
        )
    )

    thread_id = _optional_string(message.get("threadId") or message.get("thread_id"))
    subject = _string_value(message.get("subject"), default="No Subject")
    sender = _string_value(message.get("sender"), default="Unknown Sender")
    recipient = _string_value(message.get("to"), default="Unknown Recipient")
    label_ids_value = message.get("labelIds")
    label_ids = (
        [str(label_id) for label_id in label_ids_value if label_id is not None]
        if isinstance(label_ids_value, Iterable)
        and not isinstance(label_ids_value, str)
        else []
    )

    return ProcessedEmail(
        id=message_id,
        thread_id=thread_id,
        query=query,
        subject=subject,
        sender=sender,
        recipient=recipient,
        timestamp=timestamp,
        label_ids=label_ids,
        clean_text=clean_text,
        has_attachments=has_attachments,
        attachment_count=attachment_count,
        attachment_filenames=attachment_filenames,
    )


# Convert multiple raw Gmail messages into ProcessedEmail objects
def build_processed_emails(
    messages: Sequence[GmailPayload],
    *,
    query: str,
    cleaner: EmailTextCleaner | None = None,
) -> list[ProcessedEmail]:
    processed: list[ProcessedEmail] = []
    for message in messages:
        email = build_processed_email(message, query=query, cleaner=cleaner)
        if email is not None:
            processed.append(email)
    return processed


# Parse Composio Gmail API response and extract clean email data with pagination
def parse_gmail_fetch_response(
    raw_result: object,
    *,
    query: str,
    cleaner: EmailTextCleaner | None = None,
) -> tuple[list[ProcessedEmail], str | None]:
    """Convert Composio Gmail fetch payload into processed email models."""

    emails: list[ProcessedEmail] = []
    next_page: str | None = None

    containers: Sequence[object]
    if isinstance(raw_result, Mapping):
        containers = [_as_string_mapping(cast(object, raw_result)) or {}]
    elif isinstance(raw_result, list):
        containers = cast(list[object], raw_result)
    else:
        containers = []

    for raw_container in containers:
        container = _as_string_mapping(raw_container)
        if container is None:
            continue

        messages_block: Sequence[object] | None = None

        data_section = container.get("data")
        data_section_map = _as_string_mapping(data_section)
        if data_section_map is not None:
            data_section = data_section_map
            token = data_section.get("nextPageToken")
            if isinstance(token, str) and not next_page:
                next_page = token
            candidate = data_section.get("messages")
            if isinstance(candidate, list):
                messages_block = cast(list[object], candidate)

        if messages_block is None:
            candidate = container.get("messages")
            if isinstance(candidate, list):
                messages_block = cast(list[object], candidate)

        if not messages_block:
            continue

        for message in messages_block:
            message_map = _as_string_mapping(message)
            if message_map is None:
                continue
            processed = build_processed_email(message_map, query=query, cleaner=cleaner)
            if processed:
                emails.append(processed)

    return emails, next_page


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _string_value(value: object, *, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _as_string_mapping(value: object) -> Mapping[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    return {
        str(key): item for key, item in cast(Mapping[object, object], value).items()
    }


__all__ = [
    "EmailTextCleaner",
    "ProcessedEmail",
    "build_processed_email",
    "build_processed_emails",
    "convert_to_user_timezone",
    "parse_gmail_timestamp",
    "parse_gmail_fetch_response",
]
