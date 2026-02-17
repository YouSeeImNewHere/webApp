from __future__ import annotations

from db import with_db_cursor


_ACCOUNT_TOTALS_READY = False


def ensure_account_totals_cache_pg() -> None:
    """
    Ensure incremental per-account totals cache exists in Postgres.

    Cache stores, per (tenant_id, account_id):
      - start_total: sum(startingbalance.start)
      - trans_total: sum(transactions.amount)

    Triggers keep rows up to date on INSERT/UPDATE/DELETE so reads do not have to
    re-scan the full transactions table.
    """
    global _ACCOUNT_TOTALS_READY
    if _ACCOUNT_TOTALS_READY:
        return

    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS account_balance_totals (
              tenant_id INT NOT NULL DEFAULT 0,
              account_id INT NOT NULL,
              start_total DOUBLE PRECISION NOT NULL DEFAULT 0,
              trans_total DOUBLE PRECISION NOT NULL DEFAULT 0,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              PRIMARY KEY (tenant_id, account_id)
            )
            """
        )

        cur.execute(
            """
            CREATE OR REPLACE FUNCTION _account_totals_upsert_delta(
              p_tenant_id INT,
              p_account_id INT,
              p_start_delta DOUBLE PRECISION,
              p_trans_delta DOUBLE PRECISION
            ) RETURNS VOID AS $$
            BEGIN
              IF p_account_id IS NULL THEN
                RETURN;
              END IF;

              INSERT INTO account_balance_totals
                (tenant_id, account_id, start_total, trans_total, updated_at)
              VALUES
                (COALESCE(p_tenant_id, 0), p_account_id, COALESCE(p_start_delta, 0), COALESCE(p_trans_delta, 0), now())
              ON CONFLICT (tenant_id, account_id)
              DO UPDATE SET
                start_total = account_balance_totals.start_total + EXCLUDED.start_total,
                trans_total = account_balance_totals.trans_total + EXCLUDED.trans_total,
                updated_at = now();
            END;
            $$ LANGUAGE plpgsql;
            """
        )

        cur.execute(
            """
            CREATE OR REPLACE FUNCTION trg_account_totals_startingbalance()
            RETURNS TRIGGER AS $$
            BEGIN
              IF TG_OP = 'INSERT' THEN
                PERFORM _account_totals_upsert_delta(COALESCE(NEW.tenant_id, 0)::int, NEW.account_id::int, NEW.start::double precision, 0::double precision);
                RETURN NEW;
              ELSIF TG_OP = 'DELETE' THEN
                PERFORM _account_totals_upsert_delta(COALESCE(OLD.tenant_id, 0)::int, OLD.account_id::int, -(OLD.start::double precision), 0::double precision);
                RETURN OLD;
              ELSIF TG_OP = 'UPDATE' THEN
                IF COALESCE(NEW.tenant_id, 0) = COALESCE(OLD.tenant_id, 0) AND NEW.account_id = OLD.account_id THEN
                  PERFORM _account_totals_upsert_delta(COALESCE(NEW.tenant_id, 0)::int, NEW.account_id::int, (NEW.start::double precision - OLD.start::double precision), 0::double precision);
                ELSE
                  PERFORM _account_totals_upsert_delta(COALESCE(OLD.tenant_id, 0)::int, OLD.account_id::int, -(OLD.start::double precision), 0::double precision);
                  PERFORM _account_totals_upsert_delta(COALESCE(NEW.tenant_id, 0)::int, NEW.account_id::int, NEW.start::double precision, 0::double precision);
                END IF;
                RETURN NEW;
              END IF;
              RETURN NULL;
            END;
            $$ LANGUAGE plpgsql;
            """
        )

        cur.execute(
            """
            CREATE OR REPLACE FUNCTION trg_account_totals_transactions()
            RETURNS TRIGGER AS $$
            BEGIN
              IF TG_OP = 'INSERT' THEN
                PERFORM _account_totals_upsert_delta(COALESCE(NEW.tenant_id, 0)::int, NEW.account_id::int, 0::double precision, NEW.amount::double precision);
                RETURN NEW;
              ELSIF TG_OP = 'DELETE' THEN
                PERFORM _account_totals_upsert_delta(COALESCE(OLD.tenant_id, 0)::int, OLD.account_id::int, 0::double precision, -(OLD.amount::double precision));
                RETURN OLD;
              ELSIF TG_OP = 'UPDATE' THEN
                IF COALESCE(NEW.tenant_id, 0) = COALESCE(OLD.tenant_id, 0) AND NEW.account_id = OLD.account_id THEN
                  PERFORM _account_totals_upsert_delta(COALESCE(NEW.tenant_id, 0)::int, NEW.account_id::int, 0::double precision, (NEW.amount::double precision - OLD.amount::double precision));
                ELSE
                  PERFORM _account_totals_upsert_delta(COALESCE(OLD.tenant_id, 0)::int, OLD.account_id::int, 0::double precision, -(OLD.amount::double precision));
                  PERFORM _account_totals_upsert_delta(COALESCE(NEW.tenant_id, 0)::int, NEW.account_id::int, 0::double precision, NEW.amount::double precision);
                END IF;
                RETURN NEW;
              END IF;
              RETURN NULL;
            END;
            $$ LANGUAGE plpgsql;
            """
        )

        cur.execute("DROP TRIGGER IF EXISTS account_totals_startingbalance_iud ON startingbalance")
        cur.execute(
            """
            CREATE TRIGGER account_totals_startingbalance_iud
            AFTER INSERT OR UPDATE OR DELETE ON startingbalance
            FOR EACH ROW EXECUTE FUNCTION trg_account_totals_startingbalance()
            """
        )

        cur.execute("DROP TRIGGER IF EXISTS account_totals_transactions_iud ON transactions")
        cur.execute(
            """
            CREATE TRIGGER account_totals_transactions_iud
            AFTER INSERT OR UPDATE OR DELETE ON transactions
            FOR EACH ROW EXECUTE FUNCTION trg_account_totals_transactions()
            """
        )

        # Initial backfill / periodic reconciliation.
        cur.execute(
            """
            INSERT INTO account_balance_totals (tenant_id, account_id, start_total, trans_total, updated_at)
            SELECT
              src.tenant_id,
              src.account_id,
              SUM(src.start_total)::double precision AS start_total,
              SUM(src.trans_total)::double precision AS trans_total,
              now()
            FROM (
              SELECT COALESCE(tenant_id, 0)::int AS tenant_id,
                     account_id::int AS account_id,
                     COALESCE(SUM(start), 0)::double precision AS start_total,
                     0::double precision AS trans_total
              FROM startingbalance
              GROUP BY COALESCE(tenant_id, 0), account_id

              UNION ALL

              SELECT COALESCE(tenant_id, 0)::int AS tenant_id,
                     account_id::int AS account_id,
                     0::double precision AS start_total,
                     COALESCE(SUM(amount), 0)::double precision AS trans_total
              FROM transactions
              GROUP BY COALESCE(tenant_id, 0), account_id
            ) src
            GROUP BY src.tenant_id, src.account_id
            ON CONFLICT (tenant_id, account_id)
            DO UPDATE SET
              start_total = EXCLUDED.start_total,
              trans_total = EXCLUDED.trans_total,
              updated_at = now()
            """
        )

        conn.commit()

    _ACCOUNT_TOTALS_READY = True
