"""Admin registration for accounts.

Read-mostly: the email, its verification and the username belong to Auth0 and
are overwritten from the next access token, so editing them here would not
stick.
"""

from __future__ import annotations

from django.contrib import admin

from .models import Account


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("username", "email", "account_type", "business_name", "created_at")
    list_filter = ("account_type", "email_verified")
    search_fields = ("username", "email", "business_name", "user__username")
    ordering = ("-created_at",)
    readonly_fields = ("user", "email", "email_verified", "username", "created_at", "updated_at")
