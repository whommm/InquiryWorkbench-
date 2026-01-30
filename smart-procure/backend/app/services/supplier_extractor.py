"""
Supplier information extractor
Extracts structured supplier data from text strings
"""
import re
from typing import Optional, Dict


def extract_supplier_info(supplier_text: str, offer_brand: Optional[str] = None) -> Optional[Dict]:
    """
    Extract supplier information from text string

    Example input: "苏州比高机电有限公司 张三 139-8888-6666"
    Also supports: "苏州比高机电有限公司 张三 0512-12345678" (landline)

    Returns:
        Dict with keys: company_name, contact_phone, contact_name, tags
        Returns None if phone number cannot be extracted
    """
    if not supplier_text or not isinstance(supplier_text, str):
        return None

    # Remove extra whitespace
    supplier_text = " ".join(supplier_text.split())

    # Extract phone number - support multiple formats
    # 1. Mobile: 11 digits starting with 1 (e.g., 13912345678)
    # 2. Landline with area code: 0xxx-xxxxxxxx (e.g., 0512-12345678, 021-12345678)
    # 3. Landline without area code: 7-8 digits (e.g., 12345678)

    contact_phone = None
    cleaned_text = supplier_text.replace('-', '').replace(' ', '').replace('(', '').replace(')', '')

    # Try mobile number first (11 digits, starts with 1)
    mobile_pattern = r'1[3-9]\d{9}'
    mobile_match = re.search(mobile_pattern, cleaned_text)
    if mobile_match:
        contact_phone = mobile_match.group(0)
    else:
        # Try landline with area code (0xxx-xxxxxxx or 0xxxxxxxxxx)
        landline_pattern = r'0\d{2,3}[-\s]?\d{7,8}'
        landline_match = re.search(landline_pattern, supplier_text)
        if landline_match:
            contact_phone = landline_match.group(0).replace(' ', '')
        else:
            # Try plain 7-8 digit number (landline without area code)
            plain_phone_pattern = r'\b\d{7,8}\b'
            plain_match = re.search(plain_phone_pattern, cleaned_text)
            if plain_match:
                contact_phone = plain_match.group(0)

    if not contact_phone:
        return None  # Phone is required for unique identification

    # Extract company name (contains keywords like 公司, 厂, 中心, etc.)
    company_pattern = r'[\u4e00-\u9fa5]+(?:公司|厂|中心|企业|集团|工厂|有限|股份)'
    company_match = re.search(company_pattern, supplier_text)
    company_name = company_match.group(0) if company_match else "未知公司"

    # Extract contact name (2-4 Chinese characters, not part of company name)
    # Remove company name from text first
    text_without_company = supplier_text
    if company_match:
        text_without_company = supplier_text.replace(company_match.group(0), '')

    name_pattern = r'[\u4e00-\u9fa5]{2,4}'
    name_matches = re.findall(name_pattern, text_without_company)

    # Filter out common non-name words
    non_names = {'有限', '股份', '责任', '科技', '贸易', '机电', '设备', '器材'}
    contact_name = None
    for match in name_matches:
        if match not in non_names and len(match) <= 4:
            contact_name = match
            break

    # Extract tags
    tags = []
    if offer_brand and offer_brand.strip():
        tags.append(offer_brand.strip())

    return {
        "company_name": company_name,
        "contact_phone": contact_phone,
        "contact_name": contact_name,
        "tags": tags
    }
