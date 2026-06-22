def mask_name(name: str) -> str:
    """Mask each word to its initial + 4 asterisks: 'Ahmad Setiawan' -> 'A**** S****'."""
    if not name:
        return ""
    return " ".join(w[0] + "****" for w in name.split())


def mask_account_id(account_id: str) -> str:
    """Keep the last 4 chars, mask the rest. Short ids are fully masked."""
    if len(account_id) <= 4:
        return "*" * len(account_id)
    return "*" * (len(account_id) - 4) + account_id[-4:]


def mask_payment_id(payment_id: str) -> str:
    return mask_account_id(payment_id)
