# Problem 1

def converter(raw_price, raw_quantity, raw_discount):
    c_raw_price = float(raw_price)
    c_raw_quantity = int(raw_quantity)
    c_raw_discount = int(raw_discount)
    total_cost = c_raw_price * c_raw_quantity
    if c_raw_discount:
        discounted_price = total_cost - c_raw_discount
        return discounted_price
    else:
        return total_cost


print(converter(raw_price="199.99", raw_quantity="5", raw_discount="0"))


# Problem 2

def generate_llm_prompt(system_role: str, user_query: str, temperature: float):
    roles = system_role.strip().upper().split()
    return f"[{roles[0]}: {roles[1]} | TEMP : {temperature:.2f}] {user_query.strip()}"


print(generate_llm_prompt(" system assistant ", " what is rag?", 0.7))


# Problem 3

def error_checker(responses: list):

    for code in responses:
        if code is None or not code:
            continue
        if code == 500 or code == 502 or code == 503:
            print('Retrying')
        if code == 200:
            print('SUCCESS')
            break
        if code == 404:
            print("FATAL error")
            break


responses = [500, 502, 503, 200, 404]
error_checker(responses)


# Problem 4

def unique_tag_creator(logs):
    tags = []
    users = {}
    for log in logs:
        tags.extend(log.get('tags', []))
        if log.get('user') in users:
            users[log.get('user', '')].append(log.get('msg'))
        else:
            users[log.get('user')] = [log['msg']]

    return users, tags


chat_logs = [{"user": "Alice", "tags": ["python", "ai"], "msg": "Hello world"},
             {"user": "Bob", "tags": ["rag", "ai"],
                 "msg": "Building a RAG pipeline"},
             {"user": "Alice", "tags": ["python"],
                 "msg": "Learning collections"},
             ]

users, tags = unique_tag_creator(chat_logs)

print(f'{users=}, {tags=}')


# Problem 5

def add_log_entry(event: str, level: str = "INFO", logs: list[str] = None) -> list[str]:
    """
    Safely adds a log entry to the log list without mutable d
   efault bugs.
    """
    # TODO: Implement safe default initialization and append


add_log_entry()
