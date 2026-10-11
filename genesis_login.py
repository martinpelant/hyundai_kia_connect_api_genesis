import urllib.parse
import uuid
import time
import hashlib
import requests
import json
import base64

# Genesis EU Configuration
CLIENT_ID = "50e3b8b0-ced5-43b7-8a42-f86ac92fe50e"
REDIRECT_URI = "https://oneapp.genesis.com/redirect"
SCOPE = "account.token.transfer account.id.generate account.puid.userinfos account.userinfo puid name email mobileNum birthdate lang country signUpDate certProfile offline gender nationInfo account.userinfos"

def generate_login_url():
    """Generates the URL the user must visit to log in."""
    state_obj = {
        "scope": SCOPE,
        "state": None,
        "lang": "en",
        "cert": "",
        "action": "idpc_auth_endpoint",
        "country": None,
        "client_id": CLIENT_ID,
        "redirect_uri": "https://idpconnect-eu.genesis.com/auth/redirect",
        "response_type": "code",
        "signup_link": None,
        "hmgid2_client_id": CLIENT_ID,
        "hmgid2_redirect_uri": REDIRECT_URI,
        "hmgid2_scope": SCOPE,
        "hmgid2_state": "hmgoneapp",
        "hmgid2_ui_locales": "en-GB"
    }
    state_b64 = base64.b64encode(json.dumps(state_obj).encode()).decode()

    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": "https://idpconnect-eu.genesis.com/auth/redirect",
        "response_type": "code",
        "state": state_b64,
        "cert": "",
        "action": "idpc_auth_endpoint",
        "lang": "en",
        "scope": SCOPE,
        "sso_session_reset": "true"
    }

    url = "https://prd-eu-ccapi.genesis.com/api/v1/user/openid/connector/common/authorize?" + urllib.parse.urlencode(params)
    res = requests.get(url, allow_redirects=False)
    
    connector_session_key = ""
    if res.status_code == 302 and "Location" in res.headers:
        loc = res.headers["Location"]
        parsed = urllib.parse.urlparse(loc)
        qs = urllib.parse.parse_qs(parsed.query)
        if "next_uri" in qs:
            next_uri = qs["next_uri"][0]
            parsed_next = urllib.parse.urlparse(next_uri)
            qs_next = urllib.parse.parse_qs(parsed_next.query)
            if "connector_session_key" in qs_next:
                connector_session_key = qs_next["connector_session_key"][0]

    if not connector_session_key:
        print("[-] Failed to generate connector_session_key!")
        return url

    final_params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "nonce": "",
        "state": "hmgoneapp",
        "scope": SCOPE,
        "response_type": "code",
        "ui_locales": "en-GB",
        "connector_client_id": CLIENT_ID,  # Crucially without the hmgid1.0- prefix
        "connector_scope": SCOPE,
        "connector_session_key": connector_session_key,
        "country": "",
        "captcha": "1"
    }
    
    # Genesis requires space to be %20 instead of +
    qs_string = "&".join([f"{k}={urllib.parse.quote(v, safe='')}" for k, v in final_params.items()])
    return "https://idpconnect-eu.genesis.com/auth/api/v2/user/oauth2/authorize?" + qs_string

def exchange_code_for_tokens(code):
    """Exchanges the authorization code for access and refresh tokens."""
    url = f"https://cci-api-eu.genesis.com/domain/api/v1/auth/token?code={code}"
    
    device_id = str(uuid.uuid4())
    fingerprint = hashlib.sha256(device_id.encode()).hexdigest()
    timestamp = str(int(time.time() * 1000))
    
    # Use exact app User-Agent to bypass 2-hour downgrade
    ua = "Mozilla/5.0 (Linux; Android 13; sdk_gphone64_arm64 Build/TE1A.240213.009; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/109.0.5414.123 Mobile Safari/537.36 HKMCOneApp/1.0.5 (packageID=com.genesis.oneapp.eu,locale=US,lang=en-GB,platform=android,brand=genesis,theme=light,isUWB=false,isNFC=false,region=EU)/HMG_GA_AOS"

    headers = {
        'client-id': 'com.genesis.oneapp.eu',
        'client-name': 'MY GENESIS',
        'client-version': '1.0.5',
        'client-os-code': 'AOS',
        'client-os-version': '33',
        'accept-language': 'en-GB',
        'locale': 'GB',
        'timezone': 'Z',
        'app-request-id': device_id,
        'x-fingerprint': fingerprint,
        'x-timestamp': timestamp,
        'accept': 'application/json',
        'user-agent': ua
    }

    print("\n[*] Exchanging code for tokens...")
    response = requests.post(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        print("\n[+] SUCCESS! Tokens retrieved.")
        
        # Check token expiration to warn user
        try:
            import base64
            nr = data.get("nonCcsRefreshToken", "")
            if nr:
                p = nr.split('.')[1]
                p += '=' * (-len(p) % 4)
                dec = json.loads(base64.b64decode(p).decode('utf-8'))
                diff_hours = (dec['exp'] - dec['iat']) / 3600
                if diff_hours < 24:
                    print(f"\n[WARNING] Your token only has a {diff_hours:.1f}-hour lifespan!")
                    print("This means the Home Assistant integration will disconnect overnight.")
                    print("To get a 90-day token, you MUST open the login URL on a MOBILE DEVICE (phone browser)")
                    print("or use Chrome Developer Tools (Device Mode) to simulate a mobile device.\n")
                else:
                    print(f"\n[+] Excellent! You received a {diff_hours/24:.1f}-day token. It should not expire overnight.\n")
        except Exception:
            pass

        # Create the combined token string for HA
        # We prefix with 'G:' to make it easily identifiable by the library
        token_data = {
            "a": data.get("accessToken"),
            "r": data.get("refreshToken"),
            "ea": data.get("exchangeableAccessToken"),
            "er": data.get("exchangeableRefreshToken"),
            "nc": data.get("nonCcsToken"),
            "nr": data.get("nonCcsRefreshToken"),
            "it": data.get("idToken")
        }
        
        json_str = json.dumps(token_data)
        encoded_str = "G:" + base64.b64encode(json_str.encode()).decode()
        
        print("\n=== GENESIS ENCODED TOKEN STRING ===")
        print("Copy and paste the entire line below into the PASSWORD field in Home Assistant:")
        print("\n" + encoded_str + "\n")
        print("====================================\n")
        
        # Also save raw json for reference
        with open("genesis_tokens.json", "w") as f:
            json.dump(data, f, indent=4)
        print("[*] Raw tokens also saved to genesis_tokens.json")
    else:
        print("\n[-] Failed to get tokens!")
        print("Status:", response.status_code)
        print("Response:", response.text)

if __name__ == "__main__":
    print("=== Genesis EU OAuth2 Login Utility ===")
    print("This script helps you get the tokens required for the Genesis Home Assistant integration.")
    print("\n!!! CRITICAL INSTRUCTION FOR 90-DAY TOKENS !!!")
    print("The Genesis identity provider issues 2-hour tokens to standard browsers and 90-day tokens")
    print("ONLY to the official app. To trick it into giving you a 90-day token, you MUST use")
    print("Chrome Developer Tools on a desktop computer to spoof the app's User-Agent string.")
    print("----------------------------------------------")
    print("STEP 1: Open Chrome on your computer.")
    print("STEP 2: Press F12 to open Developer Tools.")
    print("STEP 3: Click the 3 dots (top right of DevTools) -> More tools -> Network conditions.")
    print("STEP 4: Uncheck 'Use browser default' next to User agent.")
    print("STEP 5: Paste the following exact string into the custom User agent box:\n")
    print("Mozilla/5.0 (Linux; Android 13; sdk_gphone64_arm64 Build/TE1A.240213.009; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/109.0.5414.123 Mobile Safari/537.36 HKMCOneApp/1.0.5 (packageID=com.genesis.oneapp.eu,locale=US,lang=en-GB,platform=android,brand=genesis,theme=light,isUWB=false,isNFC=false,region=EU)/HMG_GA_AOS\n")
    print("STEP 6: Keeping DevTools open, navigate to this URL in that tab:\n")
    print(generate_login_url() + "\n")
    print("STEP 7: Log in and solve any CAPTCHAs.")
    print("STEP 8: You will be redirected to a 'Page not found' error. Copy the ENTIRE URL from the address bar.")
    
    redirect_url = input("\nPaste the redirected URL here: ").strip()
    
    try:
        # Parse the code out of the URL
        parsed_url = urllib.parse.urlparse(redirect_url)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        code = query_params.get('code', [None])[0]
        
        if not code:
            print("[-] Could not find 'code' in the URL. Make sure you copied the entire URL including the code= part.")
        else:
            print(f"[*] Found authorization code: {code}")
            exchange_code_for_tokens(code)
            
    except Exception as e:
        print(f"[-] Error parsing URL: {e}")
