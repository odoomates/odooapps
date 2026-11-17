class RetryableJobError(Exception):
    """ Raised by a connector job to be tried again later, whatever the error is.

    :param int delay: seconds to wait before the next try; the default backoff of the queue if not given
    """

    def __init__(self, message, delay=None):
        super().__init__(message)
        self.delay = delay
