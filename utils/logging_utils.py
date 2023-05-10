import logging

# static class: root_logger

root_logger = logging.getLogger('global')
root_logger.setLevel(logging.INFO)
# root_logger.setLevel(logging.WARNING)

formatter = logging.Formatter(
    '%(asctime)s pid-%(process)d [%(levelname)s] [%(funcName)s] %(message)s - %(filename)s:%(lineno)d',
    "%m-%d %H:%M:%S"
)

stdout_handler = logging.StreamHandler()
stdout_handler.setFormatter(formatter)

root_logger.addHandler(stdout_handler)
root_logger.propagate = False

if __name__ == '__main__':
    root_logger.info('test')
