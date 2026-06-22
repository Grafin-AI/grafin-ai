from garda_ai_backend.api.masking import mask_account_id, mask_name


def test_mask_name_keeps_initials():
    assert mask_name("Ahmad Setiawan") == "A**** S****"
    assert mask_name("Budi") == "B****"
    assert mask_name("") == ""


def test_mask_account_id_keeps_last4():
    assert mask_account_id("80B779D80") == "*****9D80"
    assert mask_account_id("123") == "***"
