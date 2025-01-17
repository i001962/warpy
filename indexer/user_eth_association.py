from collections import defaultdict

from sqlalchemy import func
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from utils.models import EthTransaction, User, user_eth_transactions_association


def delete_duplicate_associations(session: Session):
    # Create a subquery to identify duplicate associations
    duplicates_subquery = session.query(
        user_eth_transactions_association.c.user_fid,
        user_eth_transactions_association.c.eth_transaction_unique_id,
        func.row_number()
        .over(
            partition_by=[
                user_eth_transactions_association.c.user_fid,
                user_eth_transactions_association.c.eth_transaction_unique_id,
            ],
            order_by=user_eth_transactions_association.c.user_fid,
        )
        .label("row_number"),
    ).subquery("duplicates_subquery")

    # Get the user_fid and eth_transaction_unique_id of duplicate rows
    duplicate_rows = (
        session.query(
            duplicates_subquery.c.user_fid,
            duplicates_subquery.c.eth_transaction_unique_id,
        )
        .filter(duplicates_subquery.c.row_number > 1)
        .all()
    )

    # Delete the duplicate rows
    affected_rows = 0
    for user_fid, eth_transaction_unique_id in duplicate_rows:
        deletion_count = (
            session.query(user_eth_transactions_association)
            .filter(
                user_eth_transactions_association.c.user_fid == user_fid,
                user_eth_transactions_association.c.eth_transaction_unique_id
                == eth_transaction_unique_id,
            )
            .delete(synchronize_session=False)
        )
        affected_rows += deletion_count
        session.commit()

    print(f"Deleted {affected_rows} duplicate rows")


def process_tx_batch(session, tx_batch, user_address_cache):
    unique_addresses = set(tx.from_address for tx in tx_batch).union(
        tx.to_address for tx in tx_batch
    )

    # Remove addresses already present in the cache
    uncached_addresses = unique_addresses - set(user_address_cache.keys())

    # Query uncached addresses
    if uncached_addresses:
        new_users = (
            session.query(User).filter(User.address.in_(uncached_addresses)).all()
        )

        # Add new users to the cache
        for user in new_users:
            user_address_cache[user.address] = user.fid

    associations_to_create = []
    for tx in tx_batch:
        from_fid = user_address_cache.get(tx.from_address)
        to_fid = user_address_cache.get(tx.to_address)

        if from_fid:
            associations_to_create.append(
                {"user_fid": from_fid, "eth_transaction_unique_id": tx.unique_id}
            )
        if to_fid and to_fid != from_fid:
            associations_to_create.append(
                {"user_fid": to_fid, "eth_transaction_unique_id": tx.unique_id}
            )

    print(f"Creating {len(associations_to_create)} associations...")

    if associations_to_create:
        for association in associations_to_create:
            session.execute(
                user_eth_transactions_association.insert().values(**association)
            )
        session.commit()


def main(engine: Engine):
    batch_size = 20000  # Decrease batch size to reduce unique_addresses count
    user_address_cache = defaultdict(int)
    last_unique_id = "0"  # Start with a character that is lexicographically smaller than any unique_id

    with sessionmaker(bind=engine)() as session:
        while True:
            tx_batch = (
                session.query(EthTransaction)
                .filter(
                    EthTransaction.unique_id > last_unique_id
                )  # Select records with unique_id lexicographically greater than the last one processed
                .order_by(EthTransaction.unique_id)
                .limit(batch_size)
                .all()
            )

            if not tx_batch:
                break

            print(f"Processing records after unique_id: {last_unique_id}")

            process_tx_batch(session, tx_batch, user_address_cache)

            # Update the last_unique_id
            last_unique_id = tx_batch[-1].unique_id

        # delete_duplicate_associations(session)
