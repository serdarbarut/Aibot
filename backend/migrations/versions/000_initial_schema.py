"""Ana tablolar için başlangıç şeması

Revision ID: 000_initial_schema
Revises:
Create Date: 2026-09-24

001-003 migrasyonlarının foreign key ile bağlandığı ana tabloları kurar
(organizations, users, ad_accounts, campaigns ...). Bu tablolar hiçbir
migrasyonda yoktu; 001 bu yüzden tek başına çalışamıyordu.

Tablolar (001-003'te kurulanlar hariç, 19 adet):
organizations, ai_usage_quotas, payment_methods, subscriptions, usage_records, users, ad_accounts, audit_logs, invitations, invoices, sessions, webhook_endpoints, ad_account_sync_logs, campaigns, webhook_deliveries, ad_copies, ai_generations, campaign_approvals, campaign_versions

Not: `ad_platform` ve `user_role` enum tipleri birden fazla tabloda
kullanıldığı için ilk kullanımda oluşturulur, sonrakilerde yeniden
oluşturulmaz (create_type=False).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '000_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('organizations',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('slug', sa.String(length=100), nullable=False),
    sa.Column('plan_tier', sa.Enum('free', 'starter', 'pro', 'agency', 'enterprise', name='plan_tier'), nullable=False),
    sa.Column('stripe_customer_id', sa.String(length=100), nullable=True),
    sa.Column('stripe_subscription_id', sa.String(length=100), nullable=True),
    sa.Column('ai_generations_used', sa.Integer(), nullable=False),
    sa.Column('ai_generations_limit', sa.Integer(), nullable=False),
    sa.Column('settings', postgresql.JSONB(astext_type=Text()), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('suspended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('suspension_reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_table('ai_usage_quotas',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('org_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('period_year', sa.Integer(), nullable=False),
    sa.Column('period_month', sa.Integer(), nullable=False),
    sa.Column('plan_tier', sa.Enum('free', 'pro', 'enterprise', name='ai_quota_plan_tier'), nullable=False),
    sa.Column('generation_limit', sa.Integer(), nullable=False),
    sa.Column('token_limit', sa.Integer(), nullable=True),
    sa.Column('generations_used', sa.Integer(), nullable=False),
    sa.Column('tokens_used', sa.Integer(), nullable=False),
    sa.Column('estimated_cost_usd', sa.Numeric(precision=10, scale=4), nullable=False),
    sa.Column('warning_sent_80', sa.Boolean(), nullable=False),
    sa.Column('warning_sent_100', sa.Boolean(), nullable=False),
    sa.Column('limit_reached_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('org_id', 'period_year', 'period_month', name='uq_ai_usage_quota_org_period')
    )
    op.create_table('payment_methods',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('org_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('stripe_payment_method_id', sa.String(length=100), nullable=False),
    sa.Column('type', sa.Enum('card', 'bank_account', 'sepa_debit', name='payment_method_type'), nullable=False),
    sa.Column('card_brand', sa.String(length=20), nullable=True),
    sa.Column('card_last4', sa.String(length=4), nullable=True),
    sa.Column('card_exp_month', sa.Integer(), nullable=True),
    sa.Column('card_exp_year', sa.Integer(), nullable=True),
    sa.Column('bank_name', sa.String(length=100), nullable=True),
    sa.Column('bank_last4', sa.String(length=4), nullable=True),
    sa.Column('is_default', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('stripe_payment_method_id')
    )
    op.create_table('subscriptions',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('org_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('stripe_subscription_id', sa.String(length=100), nullable=True),
    sa.Column('stripe_price_id', sa.String(length=100), nullable=True),
    sa.Column('stripe_product_id', sa.String(length=100), nullable=True),
    sa.Column('plan_tier', sa.Enum('free', 'starter', 'pro', 'agency', 'enterprise', name='subscription_plan_tier'), nullable=False),
    sa.Column('status', sa.Enum('active', 'past_due', 'canceled', 'incomplete', 'incomplete_expired', 'trialing', 'unpaid', 'paused', name='subscription_status'), nullable=False),
    sa.Column('billing_cycle', sa.Enum('monthly', 'yearly', name='billing_cycle'), nullable=False),
    sa.Column('amount', sa.Integer(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('current_period_start', sa.DateTime(timezone=True), nullable=True),
    sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=True),
    sa.Column('trial_start', sa.DateTime(timezone=True), nullable=True),
    sa.Column('trial_end', sa.DateTime(timezone=True), nullable=True),
    sa.Column('canceled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancel_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancel_at_period_end', sa.Boolean(), nullable=False),
    sa.Column('cancellation_reason', sa.Text(), nullable=True),
    sa.Column('extra_data', postgresql.JSONB(astext_type=Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('org_id'),
    sa.UniqueConstraint('stripe_subscription_id')
    )
    op.create_table('usage_records',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('org_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('usage_type', sa.Enum('ai_generation', 'api_request', 'report_export', 'data_sync', name='usage_type'), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
    sa.Column('stripe_usage_record_id', sa.String(length=100), nullable=True),
    sa.Column('extra_data', postgresql.JSONB(astext_type=Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('users',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('org_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=True),
    sa.Column('email_verified', sa.Boolean(), nullable=False),
    sa.Column('email_verification_token', sa.String(length=100), nullable=True),
    sa.Column('email_verification_expires', sa.DateTime(timezone=True), nullable=True),
    sa.Column('password_reset_token', sa.String(length=100), nullable=True),
    sa.Column('password_reset_expires', sa.DateTime(timezone=True), nullable=True),
    sa.Column('role', sa.Enum('admin', 'manager', 'user', name='user_role'), nullable=False),
    sa.Column('mfa_enabled', sa.Boolean(), nullable=False),
    sa.Column('mfa_secret_encrypted', sa.LargeBinary(), nullable=True),
    sa.Column('mfa_recovery_codes', postgresql.JSONB(astext_type=Text()), nullable=True),
    sa.Column('google_id', sa.String(length=100), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('failed_login_attempts', sa.Integer(), nullable=False),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_login_ip', sa.String(length=45), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('org_id', 'email', name='uq_user_org_email')
    )
    op.create_table('ad_accounts',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('org_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('platform', sa.Enum('google', 'meta', 'tiktok', name='ad_platform'), nullable=False),
    sa.Column('platform_account_id', sa.String(length=100), nullable=False),
    sa.Column('platform_account_name', sa.String(length=255), nullable=True),
    sa.Column('access_token_encrypted', sa.LargeBinary(), nullable=True),
    sa.Column('refresh_token_encrypted', sa.LargeBinary(), nullable=True),
    sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('token_scopes', postgresql.JSONB(astext_type=Text()), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('connected_by_id', sa.UUID(as_uuid=False), nullable=True),
    sa.Column('connected_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('disconnected_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('sync_status', sa.Enum('pending', 'syncing', 'success', 'error', 'auth_error', name='sync_status'), nullable=False),
    sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_sync_error', sa.Text(), nullable=True),
    sa.Column('consecutive_failures', sa.Integer(), nullable=False),
    sa.Column('extra_data', postgresql.JSONB(astext_type=Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['connected_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('org_id', 'platform', 'platform_account_id', name='uq_ad_account_org_platform_id')
    )
    op.create_table('audit_logs',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('org_id', sa.UUID(as_uuid=False), nullable=True),
    sa.Column('user_id', sa.UUID(as_uuid=False), nullable=True),
    sa.Column('action', sa.String(length=50), nullable=False),
    sa.Column('resource_type', sa.String(length=50), nullable=True),
    sa.Column('resource_id', sa.UUID(as_uuid=False), nullable=True),
    sa.Column('old_values', postgresql.JSONB(astext_type=Text()), nullable=True),
    sa.Column('new_values', postgresql.JSONB(astext_type=Text()), nullable=True),
    sa.Column('changes', postgresql.JSONB(astext_type=Text()), nullable=True),
    sa.Column('ip_address', postgresql.INET(), nullable=True),
    sa.Column('user_agent', sa.Text(), nullable=True),
    sa.Column('request_id', sa.String(length=50), nullable=True),
    sa.Column('extra_data', postgresql.JSONB(astext_type=Text()), nullable=True),
    sa.Column('impersonator_id', sa.UUID(as_uuid=False), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['impersonator_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('invitations',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('org_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('role', postgresql.ENUM('admin', 'manager', 'user', name='user_role', create_type=False), nullable=False),
    sa.Column('token', sa.String(length=100), nullable=False),
    sa.Column('invited_by_id', sa.UUID(as_uuid=False), nullable=True),
    sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['invited_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('org_id', 'email', name='uq_invitation_org_email'),
    sa.UniqueConstraint('token')
    )
    op.create_table('invoices',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('subscription_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('org_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('stripe_invoice_id', sa.String(length=100), nullable=False),
    sa.Column('stripe_payment_intent_id', sa.String(length=100), nullable=True),
    sa.Column('stripe_charge_id', sa.String(length=100), nullable=True),
    sa.Column('invoice_number', sa.String(length=50), nullable=True),
    sa.Column('status', sa.Enum('draft', 'open', 'paid', 'void', 'uncollectible', name='invoice_status'), nullable=False),
    sa.Column('amount_due', sa.Integer(), nullable=False),
    sa.Column('amount_paid', sa.Integer(), nullable=False),
    sa.Column('amount_remaining', sa.Integer(), nullable=False),
    sa.Column('subtotal', sa.Integer(), nullable=False),
    sa.Column('tax', sa.Integer(), nullable=False),
    sa.Column('total', sa.Integer(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('hosted_invoice_url', sa.Text(), nullable=True),
    sa.Column('invoice_pdf', sa.Text(), nullable=True),
    sa.Column('period_start', sa.DateTime(timezone=True), nullable=True),
    sa.Column('period_end', sa.DateTime(timezone=True), nullable=True),
    sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('line_items', postgresql.JSONB(astext_type=Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('stripe_invoice_id')
    )
    op.create_table('sessions',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('user_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('refresh_token_jti', sa.String(length=100), nullable=False),
    sa.Column('device_info', sa.String(length=255), nullable=True),
    sa.Column('ip_address', sa.String(length=45), nullable=True),
    sa.Column('user_agent', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_active_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('refresh_token_jti')
    )
    op.create_table('webhook_endpoints',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('org_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('url', sa.Text(), nullable=False),
    sa.Column('secret', sa.String(length=64), nullable=False),
    sa.Column('events', postgresql.JSONB(astext_type=Text()), nullable=False),
    sa.Column('headers', postgresql.JSONB(astext_type=Text()), nullable=False),
    sa.Column('is_enabled', sa.Boolean(), nullable=False),
    sa.Column('is_verified', sa.Boolean(), nullable=False),
    sa.Column('total_deliveries', sa.Integer(), nullable=False),
    sa.Column('successful_deliveries', sa.Integer(), nullable=False),
    sa.Column('failed_deliveries', sa.Integer(), nullable=False),
    sa.Column('last_delivery_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_delivery_status', sa.String(length=20), nullable=True),
    sa.Column('created_by_id', sa.UUID(as_uuid=False), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('ad_account_sync_logs',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('ad_account_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('sync_type', sa.String(length=50), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('duration_ms', sa.Integer(), nullable=True),
    sa.Column('records_synced', sa.Integer(), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('error_details', postgresql.JSONB(astext_type=Text()), nullable=True),
    sa.ForeignKeyConstraint(['ad_account_id'], ['ad_accounts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('campaigns',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('org_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('ad_account_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('platform', postgresql.ENUM('google', 'meta', 'tiktok', name='ad_platform', create_type=False), nullable=False),
    sa.Column('objective', sa.Enum('awareness', 'traffic', 'engagement', 'leads', 'sales', 'app_promotion', name='campaign_objective'), nullable=False),
    sa.Column('status', sa.Enum('draft', 'pending_review', 'approved', 'rejected', 'active', 'paused', 'archived', name='campaign_status'), nullable=False),
    sa.Column('status_reason', sa.Text(), nullable=True),
    sa.Column('budget_type', sa.Enum('daily', 'lifetime', name='budget_type'), nullable=False),
    sa.Column('budget_amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('budget_currency', sa.String(length=3), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=True),
    sa.Column('end_date', sa.Date(), nullable=True),
    sa.Column('is_ongoing', sa.Boolean(), nullable=False),
    sa.Column('platform_campaign_id', sa.String(length=100), nullable=True),
    sa.Column('platform_status', sa.String(length=50), nullable=True),
    sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('sync_error', sa.Text(), nullable=True),
    sa.Column('targeting', postgresql.JSONB(astext_type=Text()), nullable=True),
    sa.Column('platform_settings', postgresql.JSONB(astext_type=Text()), nullable=True),
    sa.Column('created_by_id', sa.UUID(as_uuid=False), nullable=True),
    sa.Column('updated_by_id', sa.UUID(as_uuid=False), nullable=True),
    sa.Column('approved_by_id', sa.UUID(as_uuid=False), nullable=True),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('budget_amount > 0', name='ck_campaigns_positive_budget'),
    sa.CheckConstraint('end_date IS NULL OR start_date IS NULL OR end_date >= start_date', name='ck_campaigns_valid_dates'),
    sa.ForeignKeyConstraint(['ad_account_id'], ['ad_accounts.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['approved_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('webhook_deliveries',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('endpoint_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('org_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('event_type', sa.String(length=50), nullable=False),
    sa.Column('event_id', sa.String(length=50), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=Text()), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('response_status_code', sa.Integer(), nullable=True),
    sa.Column('response_body', sa.Text(), nullable=True),
    sa.Column('response_headers', postgresql.JSONB(astext_type=Text()), nullable=True),
    sa.Column('response_time_ms', sa.Integer(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('attempt_count', sa.Integer(), nullable=False),
    sa.Column('max_attempts', sa.Integer(), nullable=False),
    sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['endpoint_id'], ['webhook_endpoints.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('ad_copies',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('campaign_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('headline_1', sa.String(length=30), nullable=False),
    sa.Column('headline_2', sa.String(length=30), nullable=True),
    sa.Column('headline_3', sa.String(length=30), nullable=True),
    sa.Column('description_1', sa.String(length=90), nullable=False),
    sa.Column('description_2', sa.String(length=90), nullable=True),
    sa.Column('path_1', sa.String(length=15), nullable=True),
    sa.Column('path_2', sa.String(length=15), nullable=True),
    sa.Column('final_url', sa.String(length=2048), nullable=False),
    sa.Column('call_to_action', sa.String(length=50), nullable=True),
    sa.Column('is_ai_generated', sa.Boolean(), nullable=False),
    sa.Column('ai_generation_id', sa.UUID(as_uuid=False), nullable=True),
    sa.Column('variation_name', sa.String(length=50), nullable=True),
    sa.Column('is_primary', sa.Boolean(), nullable=False),
    sa.Column('creative_assets', postgresql.JSONB(astext_type=Text()), nullable=True),
    sa.Column('platform_ad_id', sa.String(length=100), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('ai_generations',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('org_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('user_id', sa.UUID(as_uuid=False), nullable=True),
    sa.Column('generation_type', sa.Enum('ad_copy', 'headline', 'description', 'cta', 'targeting_suggestion', 'other', name='ai_generation_type'), nullable=False),
    sa.Column('model', sa.String(length=100), nullable=False),
    sa.Column('provider', sa.Enum('openai', 'anthropic', 'other', name='ai_provider'), nullable=False),
    sa.Column('fallback_used', sa.Boolean(), nullable=False),
    sa.Column('prompt_tokens', sa.Integer(), nullable=False),
    sa.Column('completion_tokens', sa.Integer(), nullable=False),
    sa.Column('total_tokens', sa.Integer(), nullable=False),
    sa.Column('estimated_cost_usd', sa.Numeric(precision=10, scale=6), nullable=False),
    sa.Column('generation_time_ms', sa.Integer(), nullable=False),
    sa.Column('prompt_hash', sa.String(length=64), nullable=True),
    sa.Column('input_summary', sa.Text(), nullable=True),
    sa.Column('output_summary', sa.Text(), nullable=True),
    sa.Column('status', sa.Enum('success', 'error', 'rate_limited', name='ai_generation_status'), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('campaign_id', sa.UUID(as_uuid=False), nullable=True),
    sa.Column('context', postgresql.JSONB(astext_type=Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('campaign_approvals',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('campaign_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('requested_by_id', sa.UUID(as_uuid=False), nullable=True),
    sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('decision', sa.Enum('pending', 'approved', 'rejected', name='approval_decision'), nullable=True),
    sa.Column('decided_by_id', sa.UUID(as_uuid=False), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('request_comment', sa.Text(), nullable=True),
    sa.Column('decision_comment', sa.Text(), nullable=True),
    sa.Column('campaign_version', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['decided_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['requested_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('campaign_versions',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('campaign_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('snapshot', postgresql.JSONB(astext_type=Text()), nullable=False),
    sa.Column('change_type', sa.Enum('created', 'updated', 'status_change', name='change_type'), nullable=False),
    sa.Column('change_summary', sa.Text(), nullable=True),
    sa.Column('changed_fields', postgresql.JSONB(astext_type=Text()), nullable=True),
    sa.Column('changed_by_id', sa.UUID(as_uuid=False), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['changed_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('campaign_id', 'version', name='uq_campaign_version')
    )
    op.create_index('ix_organizations_slug', 'organizations', ['slug'], unique=False)
    op.create_index('ix_organizations_stripe_customer', 'organizations', ['stripe_customer_id'], unique=False)
    op.create_index('ix_ai_usage_quotas_org_id', 'ai_usage_quotas', ['org_id'], unique=False)
    op.create_index('ix_ai_usage_quotas_period', 'ai_usage_quotas', ['period_year', 'period_month'], unique=False)
    op.create_index('ix_payment_methods_org_id', 'payment_methods', ['org_id'], unique=False)
    op.create_index('ix_payment_methods_stripe_id', 'payment_methods', ['stripe_payment_method_id'], unique=False)
    op.create_index('ix_subscriptions_org_id', 'subscriptions', ['org_id'], unique=False)
    op.create_index('ix_subscriptions_status', 'subscriptions', ['status'], unique=False)
    op.create_index('ix_subscriptions_stripe_subscription_id', 'subscriptions', ['stripe_subscription_id'], unique=False)
    op.create_index('ix_usage_records_org_id', 'usage_records', ['org_id'], unique=False)
    op.create_index('ix_usage_records_period', 'usage_records', ['period_start', 'period_end'], unique=False)
    op.create_index('ix_usage_records_type', 'usage_records', ['usage_type'], unique=False)
    op.create_index('ix_users_email', 'users', ['email'], unique=False)
    op.create_index('ix_users_google_id', 'users', ['google_id'], unique=False)
    op.create_index('ix_users_org_id', 'users', ['org_id'], unique=False)
    op.create_index('ix_ad_accounts_org_id', 'ad_accounts', ['org_id'], unique=False)
    op.create_index('ix_ad_accounts_platform', 'ad_accounts', ['platform'], unique=False)
    op.create_index('ix_ad_accounts_sync_status', 'ad_accounts', ['sync_status'], unique=False)
    op.create_index('ix_ad_accounts_token_expires', 'ad_accounts', ['token_expires_at'], unique=False)
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'], unique=False)
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'], unique=False)
    op.create_index('ix_audit_logs_org_action_created', 'audit_logs', ['org_id', 'action', 'created_at'], unique=False)
    op.create_index('ix_audit_logs_org_id', 'audit_logs', ['org_id'], unique=False)
    op.create_index('ix_audit_logs_resource', 'audit_logs', ['resource_type', 'resource_id'], unique=False)
    op.create_index('ix_audit_logs_user_id', 'audit_logs', ['user_id'], unique=False)
    op.create_index('ix_invitations_email', 'invitations', ['email'], unique=False)
    op.create_index('ix_invitations_token', 'invitations', ['token'], unique=False)
    op.create_index('ix_invoices_created_at', 'invoices', ['created_at'], unique=False)
    op.create_index('ix_invoices_org_id', 'invoices', ['org_id'], unique=False)
    op.create_index('ix_invoices_status', 'invoices', ['status'], unique=False)
    op.create_index('ix_invoices_stripe_invoice_id', 'invoices', ['stripe_invoice_id'], unique=False)
    op.create_index('ix_invoices_subscription_id', 'invoices', ['subscription_id'], unique=False)
    op.create_index('ix_sessions_expires_at', 'sessions', ['expires_at'], unique=False)
    op.create_index('ix_sessions_refresh_token_jti', 'sessions', ['refresh_token_jti'], unique=False)
    op.create_index('ix_sessions_user_id', 'sessions', ['user_id'], unique=False)
    op.create_index('ix_webhook_endpoints_is_enabled', 'webhook_endpoints', ['is_enabled'], unique=False)
    op.create_index('ix_webhook_endpoints_org_id', 'webhook_endpoints', ['org_id'], unique=False)
    op.create_index('ix_sync_logs_ad_account', 'ad_account_sync_logs', ['ad_account_id'], unique=False)
    op.create_index('ix_sync_logs_started_at', 'ad_account_sync_logs', ['started_at'], unique=False)
    op.create_index('ix_campaigns_ad_account_id', 'campaigns', ['ad_account_id'], unique=False)
    op.create_index('ix_campaigns_created_at', 'campaigns', ['created_at'], unique=False)
    op.create_index('ix_campaigns_org_id', 'campaigns', ['org_id'], unique=False)
    op.create_index('ix_campaigns_platform', 'campaigns', ['platform'], unique=False)
    op.create_index('ix_campaigns_platform_campaign_id', 'campaigns', ['platform_campaign_id'], unique=False)
    op.create_index('ix_campaigns_status', 'campaigns', ['status'], unique=False)
    op.create_index('ix_webhook_deliveries_created_at', 'webhook_deliveries', ['created_at'], unique=False)
    op.create_index('ix_webhook_deliveries_endpoint_id', 'webhook_deliveries', ['endpoint_id'], unique=False)
    op.create_index('ix_webhook_deliveries_event_type', 'webhook_deliveries', ['event_type'], unique=False)
    op.create_index('ix_webhook_deliveries_next_retry', 'webhook_deliveries', ['next_retry_at'], unique=False)
    op.create_index('ix_webhook_deliveries_org_id', 'webhook_deliveries', ['org_id'], unique=False)
    op.create_index('ix_webhook_deliveries_status', 'webhook_deliveries', ['status'], unique=False)
    op.create_index('ix_ad_copies_campaign_id', 'ad_copies', ['campaign_id'], unique=False)
    op.create_index('ix_ai_generations_created_at', 'ai_generations', ['created_at'], unique=False)
    op.create_index('ix_ai_generations_org_created', 'ai_generations', ['org_id', 'created_at'], unique=False)
    op.create_index('ix_ai_generations_org_id', 'ai_generations', ['org_id'], unique=False)
    op.create_index('ix_ai_generations_type', 'ai_generations', ['generation_type'], unique=False)
    op.create_index('ix_ai_generations_user_id', 'ai_generations', ['user_id'], unique=False)
    op.create_index('ix_campaign_approvals_campaign_id', 'campaign_approvals', ['campaign_id'], unique=False)
    op.create_index('ix_campaign_approvals_decision', 'campaign_approvals', ['decision'], unique=False)
    op.create_index('ix_campaign_approvals_requested_at', 'campaign_approvals', ['requested_at'], unique=False)
    op.create_index('ix_campaign_versions_campaign_id', 'campaign_versions', ['campaign_id'], unique=False)
    op.create_index('ix_campaign_versions_version', 'campaign_versions', ['campaign_id', 'version'], unique=False)


def downgrade() -> None:
    op.drop_table('campaign_versions')
    op.drop_table('campaign_approvals')
    op.drop_table('ai_generations')
    op.drop_table('ad_copies')
    op.drop_table('webhook_deliveries')
    op.drop_table('campaigns')
    op.drop_table('ad_account_sync_logs')
    op.drop_table('webhook_endpoints')
    op.drop_table('sessions')
    op.drop_table('invoices')
    op.drop_table('invitations')
    op.drop_table('audit_logs')
    op.drop_table('ad_accounts')
    op.drop_table('users')
    op.drop_table('usage_records')
    op.drop_table('subscriptions')
    op.drop_table('payment_methods')
    op.drop_table('ai_usage_quotas')
    op.drop_table('organizations')
    op.execute("DROP TYPE IF EXISTS ad_platform")
    op.execute("DROP TYPE IF EXISTS ai_generation_status")
    op.execute("DROP TYPE IF EXISTS ai_generation_type")
    op.execute("DROP TYPE IF EXISTS ai_provider")
    op.execute("DROP TYPE IF EXISTS ai_quota_plan_tier")
    op.execute("DROP TYPE IF EXISTS approval_decision")
    op.execute("DROP TYPE IF EXISTS billing_cycle")
    op.execute("DROP TYPE IF EXISTS budget_type")
    op.execute("DROP TYPE IF EXISTS campaign_objective")
    op.execute("DROP TYPE IF EXISTS campaign_status")
    op.execute("DROP TYPE IF EXISTS change_type")
    op.execute("DROP TYPE IF EXISTS invoice_status")
    op.execute("DROP TYPE IF EXISTS payment_method_type")
    op.execute("DROP TYPE IF EXISTS plan_tier")
    op.execute("DROP TYPE IF EXISTS subscription_plan_tier")
    op.execute("DROP TYPE IF EXISTS subscription_status")
    op.execute("DROP TYPE IF EXISTS sync_status")
    op.execute("DROP TYPE IF EXISTS usage_type")
    op.execute("DROP TYPE IF EXISTS user_role")
