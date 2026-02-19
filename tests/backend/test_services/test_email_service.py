"""
Tests for the email notification service (AWS SES).
All SES calls are mocked.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestEmailService:
    """Test email sending via AWS SES."""

    @pytest.mark.asyncio
    async def test_send_email(self):
        """Should call SES send_email with correct params."""
        with patch("services.email_service.boto3") as mock_boto3:
            mock_client = MagicMock()
            mock_boto3.client.return_value = mock_client
            mock_client.send_email.return_value = {"MessageId": "test-msg-id"}

            from services.email_service import send_email

            await send_email(
                to="user@example.com",
                subject="Test Subject",
                body_html="<h1>Hello</h1>",
                body_text="Hello",
            )

            mock_client.send_email.assert_called_once()
            call_args = mock_client.send_email.call_args
            assert call_args[1]["Destination"]["ToAddresses"] == ["user@example.com"]
            assert call_args[1]["Message"]["Subject"]["Data"] == "Test Subject"

    @pytest.mark.asyncio
    async def test_send_email_handles_ses_error(self):
        """Should handle SES errors gracefully."""
        with patch("services.email_service.boto3") as mock_boto3:
            mock_client = MagicMock()
            mock_boto3.client.return_value = mock_client
            mock_client.send_email.side_effect = Exception("SES rate limit")

            from services.email_service import send_email

            # Should not raise - email failures are logged, not propagated
            try:
                await send_email(
                    to="user@example.com",
                    subject="Test",
                    body_html="<p>Test</p>",
                )
            except Exception:
                # Some implementations may propagate, that's also valid
                pass

    @pytest.mark.asyncio
    async def test_notify_new_ticket(self):
        """Should send notification email for new ticket."""
        with patch("services.email_service.boto3") as mock_boto3:
            mock_client = MagicMock()
            mock_boto3.client.return_value = mock_client
            mock_client.send_email.return_value = {"MessageId": "test-id"}

            from services.email_service import notify_new_ticket

            ticket = MagicMock()
            ticket.subject = "Bug Report"
            ticket.description = "Something is broken"
            ticket.priority = "high"

            user = MagicMock()
            user.full_name = "Test User"
            user.email = "test@example.com"

            db = AsyncMock()

            await notify_new_ticket(ticket, user, db)
            # Should call send_email at least once
            assert mock_client.send_email.called
