class SessionCookieMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # Check if this is the sisgen search endpoint
        if request.path.startswith('/sisgen/search/'):
            # Modify any session-related cookies
            if 'sessionid' in response.cookies:
                session_cookie = response.cookies['sessionid']
                session_cookie['samesite'] = 'None'
                session_cookie['secure'] = True
                session_cookie['httponly'] = True
                
                # Add Partitioned attribute through header
                if 'Set-Cookie' in response.headers:
                    cookies = response.headers['Set-Cookie'].split('\n')
                    new_cookies = []
                    for cookie in cookies:
                        if 'sessionid' in cookie:
                            cookie += '; Partitioned'
                        new_cookies.append(cookie)
                    response.headers['Set-Cookie'] = '\n'.join(new_cookies)
                
            if 'csrftoken' in response.cookies:
                csrf_cookie = response.cookies['csrftoken']
                csrf_cookie['samesite'] = 'None'
                csrf_cookie['secure'] = True
                csrf_cookie['httponly'] = True
        
        return response 