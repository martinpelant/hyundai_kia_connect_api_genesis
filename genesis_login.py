import urllib.parse
import uuid
import time
import requests
import json

# Genesis EU Configuration
CLIENT_ID = "50e3b8b0-ced5-43b7-8a42-f86ac92fe50e"
REDIRECT_URI = "https://oneapp.genesis.com/redirect"
SCOPE = "account.token.transfer account.id.generate account.puid.userinfos account.userinfo read account.userinfos puid email name mobileNum birthdate lang country signUpDate gender nationInfo certProfile offline"

def generate_login_url():
    """Generates the URL the user must visit to log in."""
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "state": "hmgoneapp",
        "ui_locales": "en-GB"
    }
    url = "https://idpconnect-eu.genesis.com/auth/api/v2/user/oauth2/authorize?" + urllib.parse.urlencode(params)
    return url

def exchange_code_for_tokens(code):
    """Exchanges the authorization code for access and refresh tokens."""
    url = f"https://cci-api-eu.genesis.com/domain/api/v1/auth/token?code={code}"
    
    headers = {
        'client-id': 'com.genesis.oneapp.eu',
        'client-name': 'MY GENESIS',
        'client-version': '1.0.5',
        'client-os-code': 'AOS',
        'client-os-version': '33',
        'accept-language': 'en-GB',
        'locale': 'GB',
        'timezone': 'Z',
        'app-request-id': str(uuid.uuid4()),
        'accept': 'application/json',
        'user-agent': 'Ktor client'
    }

    print("\n[*] Exchanging code for tokens...")
    response = requests.post(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        print("\n[+] SUCCESS! Tokens retrieved:\n")
        print("AccessToken (GSPA):", str(data.get("accessToken"))[:50] + "...")
        print("RefreshToken (GSPA):", data.get("refreshToken"))
        print("\nAccessToken (IDP):", str(data.get("nonCcsToken"))[:50] + "...")
        print("RefreshToken (IDP):", data.get("nonCcsRefreshToken"))
        
        # Save to file
        with open("genesis_tokens.json", "w") as f:
            json.dump(data, f, indent=4)
        print("\n[*] Tokens saved to genesis_tokens.json")
    else:
        print("\n[-] Failed to get tokens!")
        print("Status:", response.status_code)
        print("Response:", response.text)

if __name__ == "__main__":
    print("=== Genesis EU OAuth2 Login ===")
    print("1. Open this URL in your web browser (you can use your computer's browser):")
    print("\n" + generate_login_url() + "\n")
    print("2. Log in with your Genesis account and solve the CAPTCHA.")
    print("3. You will eventually be redirected to a blank page or a 'site cannot be reached' error.")
    print("4. Copy the ENTIRE URL from your browser's address bar (it should start with https://oneapp.genesis.com/redirect?code=...)")
    
    redirect_url = input("\nPaste the redirected URL here: ").strip()
    
    try:
        # Parse the code out of the URL
        parsed_url = urllib.parse.urlparse(redirect_url)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        code = query_params.get('code', [None])[0]
        
        if not code:
            print("[-] Could not find 'code' in the URL. Make sure you copied the whole thing.")
        else:
            print(f"[*] Found authorization code: {code}")
            exchange_code_for_tokens(code)
            
    except Exception as e:
        print(f"[-] Error parsing URL: {e}")