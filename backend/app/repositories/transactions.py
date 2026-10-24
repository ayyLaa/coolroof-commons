from typing import TypeAlias

from sqlalchemy.orm import Session

# Services only forward this handle; persistence details stay in repositories.
RepositoryContext: TypeAlias = Session


def commit(context: RepositoryContext) -> None:
    context.commit()
