"""Read-only broker account lifecycle and sync commands."""

from datetime import datetime


class BrokerCommands:
    def broker_register_snaptrade_user(
        self,
        user_key: str,
        provider_user_id: str | None = None,
    ):
        """
        Register and store a SnapTrade user for read-only broker linking.
        """
        user_key = self._broker_required_user_key(user_key)
        provider_user_id = provider_user_id.strip() if provider_user_id else user_key

        user = self._snaptrade_provider().register_user(provider_user_id)
        user = type(user)(
            provider=user.provider,
            user_key=user_key,
            provider_user_id=user.provider_user_id,
            user_secret=user.user_secret,
            status=user.status,
        )
        repo, cipher = self._broker_repo_and_cipher()
        repo.upsert_broker_user(user, cipher)
        return user

    def broker_snaptrade_portal(
        self,
        user_key: str,
        broker: str | None = None,
        custom_redirect: str | None = None,
        immediate_redirect: bool = False,
        register_if_missing: bool = False,
        reconnect: str | None = None,
    ):
        """
        Create a SnapTrade hosted portal URL with read-only account permissions.
        """
        user_key = self._broker_required_user_key(user_key)
        user = self._get_snaptrade_user(user_key)
        if user is None:
            if not register_if_missing:
                raise ValueError(
                    "No SnapTrade user found. Run broker snaptrade register-user first, "
                    "or pass --register-if-missing."
                )
            user = self.broker_register_snaptrade_user(user_key)

        return self._snaptrade_provider().create_connection_portal(
            user,
            broker=broker,
            custom_redirect=custom_redirect,
            immediate_redirect=immediate_redirect,
            reconnect=reconnect,
        )

    def broker_snaptrade_rotate_secret(self, user_key: str):
        repo, cipher = self._broker_repo_and_cipher()
        user = self._get_snaptrade_user(user_key)
        if user is None:
            raise ValueError(f"No SnapTrade user found: {user_key}")
        rotated = self._snaptrade_provider().rotate_user_secret(user)
        repo.upsert_broker_user(rotated, cipher)
        return rotated

    def broker_snaptrade_unlink_user(self, user_key: str, delete_provider_user: bool = False):
        from dashboard.brokers.snaptrade import SNAPTRADE_PROVIDER

        repo, _cipher = self._broker_repo_and_cipher()
        user = self._get_snaptrade_user(user_key)
        if user is None:
            raise ValueError(f"No SnapTrade user found: {user_key}")
        provider_response = None
        if delete_provider_user:
            provider_response = self._snaptrade_provider().delete_user(user)
        repo.update_broker_user_status(SNAPTRADE_PROVIDER, user.user_key, "unlinked")
        return provider_response

    def broker_snaptrade_disable_connection(self, user_key: str, provider_connection_id: str):
        from dashboard.brokers.models import BrokerConnection
        from dashboard.brokers.snaptrade import SNAPTRADE_PROVIDER

        repo, _cipher = self._broker_repo_and_cipher()
        user = self._get_snaptrade_user(user_key)
        if user is None:
            raise ValueError(f"No SnapTrade user found: {user_key}")
        connection = BrokerConnection(
            provider=SNAPTRADE_PROVIDER,
            provider_connection_id=provider_connection_id.strip(),
            institution_name="unknown",
            status="unknown",
            provider_user_id=user.provider_user_id,
        )
        self._snaptrade_provider().disconnect(user, connection)
        repo.update_connection_status(
            SNAPTRADE_PROVIDER,
            provider_connection_id.strip(),
            "disabled",
        )

    def broker_snaptrade_smoke_test(self, user_key: str | None = None):
        from dashboard.brokers.models import BrokerSmokeTestResult
        from dashboard.brokers.snaptrade import SNAPTRADE_PROVIDER, SnapTradeError

        try:
            status = self._snaptrade_provider().api_status()
            api_online = bool(status.get("online", True))
        except Exception as exc:
            return BrokerSmokeTestResult(
                provider=SNAPTRADE_PROVIDER,
                api_online=False,
                configured=False,
                user_found=False,
                message=str(exc),
            )

        user_found = False
        if user_key:
            try:
                user_found = self._get_snaptrade_user(user_key) is not None
            except (SnapTradeError, ValueError) as exc:
                return BrokerSmokeTestResult(
                    provider=SNAPTRADE_PROVIDER,
                    api_online=api_online,
                    configured=True,
                    user_found=False,
                    message=str(exc),
                )

        return BrokerSmokeTestResult(
            provider=SNAPTRADE_PROVIDER,
            api_online=api_online,
            configured=True,
            user_found=user_found,
            message="snaptrade credentials are reachable",
        )

    def broker_snaptrade_sync(
        self,
        user_key: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ):
        from dashboard.brokers.portfolio import BrokerPortfolioIntegrationService
        from dashboard.brokers.snaptrade import SNAPTRADE_PROVIDER
        from dashboard.brokers.sync import BrokerSyncService

        repo, cipher = self._broker_repo_and_cipher()
        service = BrokerSyncService(
            repo,
            self._snaptrade_provider(),
            cipher,
        )
        result = service.sync_user(
            user_key.strip(),
            start_date=self._broker_parse_date(start_date),
            end_date=self._broker_parse_date(end_date),
        )
        portfolio_service = BrokerPortfolioIntegrationService(self.conn)
        for account in repo.list_accounts(SNAPTRADE_PROVIDER):
            if account.portfolio_id is None:
                continue
            portfolio_service.project_account_positions(
                provider_account_id=account.provider_account_id,
                portfolio_id=account.portfolio_id,
                provider=SNAPTRADE_PROVIDER,
            )
        return result

    def broker_snaptrade_sync_due(
        self,
        max_users: int | None = None,
        min_age_hours: int = 24,
        force: bool = False,
    ):
        from dashboard.brokers.scheduler import BrokerSyncScheduler

        repo, cipher = self._broker_repo_and_cipher()
        scheduler = BrokerSyncScheduler(
            repo,
            self._snaptrade_provider(),
            cipher,
        )
        return scheduler.sync_due_users(
            max_users=max_users,
            min_age_hours=min_age_hours,
            force=force,
        )

    def broker_accounts(self, provider: str = "snaptrade"):
        return self._broker_repo().list_accounts(provider)

    def broker_map_account(
        self,
        provider_account_id: str,
        portfolio_id: int,
        provider: str = "snaptrade",
    ):
        from dashboard.brokers.portfolio import BrokerPortfolioIntegrationService

        if not self.conn.execute(
            "SELECT 1 FROM portfolio WHERE portfolio_id = ?",
            [portfolio_id],
        ).fetchone():
            raise ValueError(f"Portfolio not found: {portfolio_id}")
        self._broker_repo().map_account_to_portfolio(
            provider,
            provider_account_id.strip(),
            portfolio_id,
        )
        return BrokerPortfolioIntegrationService(self.conn).project_account_positions(
            provider_account_id=provider_account_id.strip(),
            portfolio_id=portfolio_id,
            provider=provider,
        )

    def broker_import_transactions(
        self,
        provider: str = "snaptrade",
        portfolio_id: int | None = None,
    ):
        from dashboard.brokers.portfolio import BrokerPortfolioIntegrationService

        if (
            portfolio_id is not None
            and not self.conn.execute(
                "SELECT 1 FROM portfolio WHERE portfolio_id = ?",
                [portfolio_id],
            ).fetchone()
        ):
            raise ValueError(f"Portfolio not found: {portfolio_id}")
        return BrokerPortfolioIntegrationService(self.conn).import_mapped_transactions(
            provider=provider,
            portfolio_id=portfolio_id,
        )

    def broker_raw_payload_storage_enabled(self) -> bool:
        return self._broker_repo().raw_payload_storage_enabled()

    def set_broker_raw_payload_storage_enabled(self, enabled: bool) -> None:
        self._broker_repo().set_raw_payload_storage_enabled(enabled)

    @staticmethod
    def _snaptrade_config():
        from dashboard.brokers.snaptrade import SnapTradeConfig

        return SnapTradeConfig.from_env()

    def _snaptrade_provider(self):
        from dashboard.brokers.snaptrade import SnapTradeProvider

        return SnapTradeProvider(self._snaptrade_config())

    def _broker_repo_and_cipher(self):
        return self._broker_repo(), self._broker_secret_cipher()

    def _broker_repo(self):
        from dashboard.brokers.repository import BrokerSyncRepository

        return BrokerSyncRepository(self.conn)

    def _get_snaptrade_user(self, user_key: str):
        from dashboard.brokers.snaptrade import SNAPTRADE_PROVIDER

        repo, cipher = self._broker_repo_and_cipher()
        return repo.get_broker_user(
            SNAPTRADE_PROVIDER,
            self._broker_required_user_key(user_key),
            cipher,
        )

    @staticmethod
    def _broker_required_user_key(user_key: str) -> str:
        user_key = user_key.strip()
        if not user_key:
            raise ValueError("Broker user key is required.")
        return user_key

    @staticmethod
    def _broker_secret_cipher():
        import os

        from dotenv import load_dotenv

        from dashboard.brokers.secrets import LocalSecretCipher

        load_dotenv()
        key = os.getenv("QUAINT_BROKER_SECRET_KEY")
        if not key:
            raise ValueError("QUAINT_BROKER_SECRET_KEY is required for broker secret storage.")
        return LocalSecretCipher(key)

    @staticmethod
    def _broker_parse_date(value: str | None):
        if value is None:
            return None
        for fmt in ("%Y-%m-%d", "%m-%d-%Y", "%m/%d/%Y"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        raise ValueError(f"Date {value} invalid. Use YYYY-MM-DD, MM-DD-YYYY, or MM/DD/YYYY.")

    #######################################################################
    ##              daily ingestion and historical backfill
    #######################################################################
