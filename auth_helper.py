
import hashlib
import hmac
import json
from urllib.parse import parse_qsl


def validate_init_data(init_data: str, bot_token: str) -> dict:
    """
    Validates the Telegram Web App initData string.
    Returns the parsed data as a dict if valid, otherwise raises ValueError.
    """
    try:
        parsed_data = dict(parse_qsl(init_data))
    except ValueError:
        raise ValueError("Invalid init_data format")

    if 'hash' not in parsed_data:
        raise ValueError("Missing hash")

    hash_check = parsed_data.pop('hash')
    
    # Data-check-string is a chain of all received fields, sorted alphabetically
    # in the format key=<value> with a line feed character ('\n') as separator
    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(parsed_data.items())
    )
    
    # Calculate HMAC-SHA-256 signature
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if calculated_hash != hash_check:
        raise ValueError("Invalid hash")

    # If valid, return parsed data. 'user' field is a JSON string, parse it too.
    if 'user' in parsed_data:
        parsed_data['user'] = json.loads(parsed_data['user'])
        
    return parsed_data

def validate_widget_auth(data: dict, bot_token: str) -> bool:
    """
    Validates the Telegram Login Widget data.
    data expected to contain: id, first_name, ... and hash.
    Returns True if valid, raises ValueError if not.
    """
    if 'hash' not in data:
        raise ValueError("Missing hash")

    received_hash = data.pop('hash')
    
    # Filter out None values just in case, though widget usually sends strings
    data_check_arr = []
    for key, value in sorted(data.items()):
        if value is not None:
             data_check_arr.append(f"{key}={value}")
             
    data_check_string = "\n".join(data_check_arr)
    
    # Widget signature: HMAC-SHA-256 using SHA-256(bot_token) as secret
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    
    if calculated_hash != received_hash:
        raise ValueError("Invalid hash")
        
    return True
