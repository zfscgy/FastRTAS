import threading


def parallel(funcs, params):
    threads = []
    errors = []

    def func_wrapper(func, params):
        try:
            func(*params)
        except Exception as e:
            errors.append(e)

    if isinstance(funcs, list):
        for func, param in zip(funcs, params):
            threads.append(threading.Thread(target=func_wrapper, args=(func, param)))
    else:
        for param in params:
            threads.append(threading.Thread(target=func_wrapper, args=(funcs, param)))
            threads[-1].start()
    for thread in threads:
        thread.join()
    if len(errors) == 0:
        return None
    else:
        return errors