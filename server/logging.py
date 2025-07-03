import logging
from gunicorn.glogging import Logger

class CustomGunicornLogger(Logger):
    """
    A custom Gunicorn logger that filters out Kubernetes health check probes
    from the access logs.
    """
    def setup(self, cfg):
        """
        This method is called by Gunicorn at startup to configure logging.
        """
        super().setup(cfg)

        # --- THIS IS THE FIX ---
        # Get the Flask application's logger
        app_logger = logging.getLogger('flask.app')

        # Add all of Gunicorn's handlers to the Flask logger.
        # This makes Flask's debug messages go to the same place as Gunicorn's logs.
        for handler in self.error_log.handlers:
            app_logger.addHandler(handler)
        
        # Finally, ensure the Flask logger is set to DEBUG level.
        app_logger.setLevel(logging.DEBUG)

    def access(self, resp, req, environ, request_time):
        """
        This method is called by Gunicorn to log an access request.
        We check the User-Agent here and simply return without logging
        if it matches a Kubernetes probe to explicitly the healthz URL.
        """
        # Get the User-Agent header from the request environment
        user_agent: str = environ.get("HTTP_USER_AGENT", "")

        if user_agent.startswith('kube-probe/') and req.method == 'GET' and req.path == '/healthz':
            return

        super().access(resp, req, environ, request_time)