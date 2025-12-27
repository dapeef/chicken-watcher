from hardware_agent.db.repository import insert_chicken


def test_insert_chicken():
    insert_chicken("Test name")
