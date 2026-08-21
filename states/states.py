from aiogram.fsm.state import State, StatesGroup


class CatalogStates(StatesGroup):
    viewing_photos = State()


class CheckoutStates(StatesGroup):
    choosing_data_mode = State()
    collecting_name = State()
    collecting_phone = State()
    collecting_phone_manual = State()
    collecting_city = State()
    collecting_pickup_point = State()
    collecting_comment = State()
    confirming_order = State()


class PaymentStates(StatesGroup):
    waiting_receipt = State()


class AdminStates(StatesGroup):
    viewing_order = State()
    waiting_rejection_comment = State()
    waiting_track_number = State()
    waiting_status_change = State()

    waiting_photo_upload = State()
    waiting_photo_number = State()
    waiting_item_price = State()
    waiting_item_stock = State()
    select_category_for_item = State()
    select_item_to_edit = State()
    waiting_infographic_upload = State()

    waiting_new_delivery_cost = State()
    waiting_new_requisites = State()
    waiting_new_pickup_address = State()
    waiting_new_manager_contact = State()
    waiting_new_category_price = State()

    waiting_new_payment_card = State()
    waiting_new_payment_phone_sbp = State()
    waiting_new_payment_wallet = State()
    waiting_new_payment_recipient_name = State()
