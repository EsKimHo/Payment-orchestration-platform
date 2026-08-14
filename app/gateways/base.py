from abc import ABC, abstractmethod #abc means abstract base class, which is a class that cannot be instantiated on its own and is meant to be subclassed by other classes. It can contain abstract methods that must be implemented by any concrete subclass.

class PaymentGateway(ABC):
    @abstractmethod
    def charge(self, amount: int, currency: str) -> dict:
        """Attempt a charge. Returns {'status': 'success'|'failure', 'transaction_id': str|None}."""
        ...

    @abstractmethod
    def get_status(self, transaction_id: str) -> dict:
        """Check the status of a previous charge."""
        ...