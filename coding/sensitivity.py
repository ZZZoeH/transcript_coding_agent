"""Conservative derived information tiers from appendix Table 2, not model guesses."""
# Open qualification labels not covered by Table 2 remain explicitly unmapped.
GROUPS = {
 "T1": "name name_doctor name_mother age city state ssn_state zip_code county country citizenship gender",
 "T2": "address address_home address_clinic address_pharmacy address_po_box address_work phone_number callback_number phone_alternative phone_family phone_friend business_number line_number email dob birthplace debt_status debt_amount debt_type tax_debt_amount bankruptcy loan_amount loan annual_income monthly_income household_income disability_income employment_status occupation_duration social_security ss_money ss_money_date ssdi bank_provider bank_account_balance bank_account_holder bank_account_type bank_provider_duration credit_score credit_history insurance_carrier health_insurance_source health_insurance_type pharmacy_provider pharmacy_carrier verizon_account_number service_id account_access_location accountownership beneficiary dob_beneficiary phone_beneficiary name_beneficiary age_beneficiary emergency_contact license_plate_number license_plate_state vehicle_vin_number driver_license_age payment payment_date payment_type monthly_payment monthly_mortgage_payment insurance_payment medication_payment down_payment_amount copay enrollment_automatic_payment donation donation_amount medicare_detail medicare_duration medicare_effective_date medicare_expiration medicare_info_ready medicare_reason medicare_satisfaction medicare_update_date name_medicare_card credit_card_balance credit_card_holder credit_card_type name_credit_card",
 "T3": "ssn driver_license_id vehicle_registration medicare_id bank_account_number routing_number credit_card_number cvv_number credit_card_expiration credit_card_expiration_date password password_email",
}
TIERS = {label: tier for tier, words in GROUPS.items() for label in words.split()}


def classify(labels):
    return {label: TIERS.get(label, "unmapped") for label in labels}
