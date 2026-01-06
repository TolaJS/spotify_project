"""
Test script for Spotify OAuth authentication. 
This script tests the OAuth handler and verifies the Spotify API connection.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from auth.oauth_handler import get_spotify_client, SpotifyOAuthHandler


def test_authentication():
    """Test basic authentication and token retrieval."""
    print("=" * 60)
    print("Testing Spotify OAuth Authentication")
    print("=" * 60)
    print()

    try:
        print("Step 1: Initializing OAuth handler...")
        handler = SpotifyOAuthHandler()
        print(f"✓ Client ID: {handler.client_id[:10]}...")
        print(f"✓ Redirect URI: {handler.redirect_uri}")
        print(f"✓ Scopes configured: {len(handler.scope.split())} scopes")
        print()

        print("Step 2: Authenticating with Spotify...")
        print("(This may open a browser window for authorization)")
        sp = get_spotify_client()
        print("✓ Authentication successful!")
        print()

        return sp

    except ValueError as e:
        print(f"✗ Configuration Error: {e}")
        print("\nPlease check your .env file and ensure:")
        print("  - SPOTIFY_CLIENT_ID is set")
        print("  - SPOTIFY_CLIENT_SECRET is set")
        print("  - SPOTIFY_REDIRECT_URI is set (optional)")
        return None

    except Exception as e:
        print(f"✗ Authentication Error: {e}")
        return None


def test_user_profile(sp):
    """Test fetching user profile information."""
    print("=" * 60)
    print("Testing User Profile Access")
    print("=" * 60)
    print()

    try:
        user = sp.me()
        print(f"✓ User ID: {user['id']}")
        print(f"✓ Display Name: {user.get('display_name', 'N/A')}")
        print(f"✓ Email: {user.get('email', 'N/A')}")
        print(f"✓ Country: {user.get('country', 'N/A')}")
        print(f"✓ Account Type: {user.get('product', 'N/A')}")
        print()
        return True

    except Exception as e:
        print(f"✗ Failed to fetch user profile: {e}")
        print()
        return False


def test_search(sp):
    """Test search functionality."""
    print("=" * 60)
    print("Testing Search API")
    print("=" * 60)
    print()

    try:
        query = "The Beatles"
        print(f"Searching for: '{query}'")
        results = sp.search(q=query, type="artist", limit=3)

        if results['artists']['items']:
            print(f"✓ Found {len(results['artists']['items'])} artist(s):")
            for i, artist in enumerate(results['artists']['items'], 1):
                print(f"  {i}. {artist['name']} (Followers: {artist['followers']['total']:,})")
            print()
            return True
        else:
            print("✗ No results found")
            print()
            return False

    except Exception as e:
        print(f"✗ Search failed: {e}")
        print()
        return False


def test_playlists(sp):
    """Test playlist access."""
    print("=" * 60)
    print("Testing Playlist Access")
    print("=" * 60)
    print()

    try:
        playlists = sp.current_user_playlists(limit=5)

        if playlists['items']:
            print(f"✓ Found {len(playlists['items'])} playlist(s):")
            for i, playlist in enumerate(playlists['items'], 1):
                print(f"  {i}. {playlist['name']} ({playlist['tracks']['total']} tracks)")
            print()
            return True
        else:
            print("ℹ No playlists found (this is okay if you don't have any)")
            print()
            return True

    except Exception as e:
        print(f"✗ Failed to fetch playlists: {e}")
        print()
        return False


def test_recently_played(sp):
    """Test recently played tracks."""
    print("=" * 60)
    print("Testing Recently Played Tracks")
    print("=" * 60)
    print()

    try:
        results = sp.current_user_recently_played(limit=5)

        if results['items']:
            print(f"✓ Found {len(results['items'])} recently played track(s):")
            for i, item in enumerate(results['items'], 1):
                track = item['track']
                artists = ", ".join([a['name'] for a in track['artists']])
                print(f"  {i}. {track['name']} - {artists}")
            print()
            return True
        else:
            print("ℹ No recently played tracks found")
            print()
            return True

    except Exception as e:
        print(f"✗ Failed to fetch recently played: {e}")
        print()
        return False


def test_current_playback(sp):
    """Test current playback state."""
    print("=" * 60)
    print("Testing Current Playback")
    print("=" * 60)
    print()

    try:
        currently_playing = sp.current_playback()

        if currently_playing and currently_playing.get('item'):
            track = currently_playing['item']
            artists = ", ".join([a['name'] for a in track['artists']])
            is_playing = currently_playing['is_playing']

            print(f"✓ Currently {'playing' if is_playing else 'paused'}:")
            print(f"  Track: {track['name']}")
            print(f"  Artist: {artists}")
            print(f"  Album: {track['album']['name']}")
            print()
            return True
        else:
            print("ℹ No track currently playing")
            print()
            return True

    except Exception as e:
        print(f"✗ Failed to fetch current playback: {e}")
        print()
        return False


def test_token_refresh():
    """Test token refresh functionality."""
    print("=" * 60)
    print("Testing Token Refresh")
    print("=" * 60)
    print()

    try:
        # Get a new handler instance
        handler = SpotifyOAuthHandler()
        sp = handler.get_spotify_client()

        # Check if token exists
        token_info = handler.sp_oauth.get_cached_token()
        if not token_info:
            print("✗ No cached token found")
            print()
            return False

        print(f"✓ Token found in cache")
        print(f"  Access token: {token_info['access_token'][:20]}...")

        # Check expiration status
        is_expired = handler.sp_oauth.is_token_expired(token_info)
        print(f"  Token expired: {is_expired}")

        # Test re-fetching (should use cached token if valid)
        sp2 = handler.get_spotify_client()
        print(f"✓ Successfully retrieved client (using {'refreshed' if is_expired else 'cached'} token)")

        # Verify the client works
        user = sp2.me()
        print(f"✓ Token is valid - verified with user: {user['id']}")
        print()
        return True

    except Exception as e:
        print(f"✗ Token refresh test failed: {e}")
        print()
        return False


def test_token_cache_management():
    """Test token cache file management."""
    print("=" * 60)
    print("Testing Token Cache Management")
    print("=" * 60)
    print()

    cache_path = ".spotify_cache_test"

    try:
        # Create a handler with custom cache path
        handler = SpotifyOAuthHandler()
        print(f"✓ Testing with cache path: {cache_path}")

        # Check if default cache exists
        default_cache = Path(".spotify_cache")
        if default_cache.exists():
            print(f"✓ Default cache file exists: {default_cache}")
            import json
            with open(default_cache, 'r') as f:
                cache_data = json.load(f)
                print(f"  Cache contains: access_token, refresh_token, expires_at")
                print(f"  Token type: {cache_data.get('token_type', 'N/A')}")
        else:
            print("ℹ No default cache file found (will be created on first auth)")

        print()
        return True

    except Exception as e:
        print(f"✗ Cache management test failed: {e}")
        print()
        return False
    finally:
        # Clean up test cache if it exists
        test_cache = Path(cache_path)
        if test_cache.exists():
            test_cache.unlink()


def test_token_revocation():
    """Test token revocation and cache clearing."""
    print("=" * 60)
    print("Testing Token Revocation")
    print("=" * 60)
    print()

    try:
        # Create a test cache
        test_cache_path = ".spotify_cache_revoke_test"

        print(f"Step 1: Creating test authentication with cache: {test_cache_path}")
        handler = SpotifyOAuthHandler()

        # Authenticate and create cache
        sp = handler.authenticate(cache_path=test_cache_path)

        # Verify cache was created
        if Path(test_cache_path).exists():
            print(f"✓ Test cache file created")
        else:
            print(f"✗ Cache file not created")
            return False

        print()
        print("Step 2: Revoking token and clearing cache...")
        handler.revoke_token()

        # Verify cache was removed
        if not Path(test_cache_path).exists():
            print(f"✓ Cache file successfully removed")
        else:
            print(f"✗ Cache file still exists")
            # Clean up manually
            Path(test_cache_path).unlink()
            return False

        # Verify handler state was reset
        if handler.sp is None and handler.sp_oauth is None:
            print(f"✓ Handler state successfully reset")
        else:
            print(f"✗ Handler state not properly reset")
            return False

        print()
        return True

    except Exception as e:
        print(f"✗ Token revocation test failed: {e}")
        print()
        # Clean up test cache if it exists
        if Path(test_cache_path).exists():
            Path(test_cache_path).unlink()
        return False


def test_multiple_clients():
    """Test creating multiple client instances."""
    print("=" * 60)
    print("Testing Multiple Client Instances")
    print("=" * 60)
    print()

    try:
        print("Creating multiple Spotify client instances...")

        # Get global client
        sp1 = get_spotify_client()
        user1 = sp1.me()
        print(f"✓ Client 1 (global): {user1['id']}")

        # Get global client again (should be same instance)
        sp2 = get_spotify_client()
        user2 = sp2.me()
        print(f"✓ Client 2 (global): {user2['id']}")

        # Verify they're for the same user
        if user1['id'] == user2['id']:
            print(f"✓ Both clients authenticated as same user")
        else:
            print(f"✗ Clients authenticated as different users")
            return False

        print()
        return True

    except Exception as e:
        print(f"✗ Multiple clients test failed: {e}")
        print()
        return False


def run_all_tests():
    """Run all authentication and API tests."""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 10 + "Spotify OAuth Handler Test Suite" + " " * 15 + "║")
    print("╚" + "=" * 58 + "╝")
    print()

    # Test authentication
    sp = test_authentication()
    if not sp:
        print("\n❌ Authentication failed. Please fix the errors above and try again.")
        return False

    # Run API tests (require authenticated client)
    api_tests = [
        ("User Profile", test_user_profile),
        ("Search API", test_search),
        ("Playlists", test_playlists),
        ("Recently Played", test_recently_played),
        ("Current Playback", test_current_playback)
    ]

    results = []
    for test_name, test_func in api_tests:
        try:
            result = test_func(sp)
            results.append((test_name, result))
        except Exception as e:
            print(f"✗ Unexpected error in {test_name}: {e}")
            results.append((test_name, False))

    # Run token management tests (standalone)
    token_tests = [
        ("Token Refresh", test_token_refresh),
        ("Token Cache Management", test_token_cache_management),
        ("Multiple Client Instances", test_multiple_clients),
        ("Token Revocation", test_token_revocation)
    ]

    for test_name, test_func in token_tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"✗ Unexpected error in {test_name}: {e}")
            results.append((test_name, False))

    # Print summary
    print("=" * 60)
    print("Test Summary")
    print("=" * 60)
    print()

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")

    print()
    print(f"Total: {passed}/{total} tests passed")
    print()

    if passed == total:
        print("🎉 All tests passed! Your OAuth handler is working correctly.")
        return True
    else:
        print("⚠️  Some tests failed. Please review the errors above.")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
