import queue
import sqlite3
import threading

from daylens.repositories import connection_repository


def test_shared_read_connection_is_reused_only_by_its_creating_thread(tmp_path):
    db_path = tmp_path / "threaded.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE samples (value TEXT)")
    conn.execute("INSERT INTO samples VALUES ('ok')")
    conn.commit()
    conn.close()

    connection_repository.init_shared_read_conn(str(db_path))
    try:
        with connection_repository.read_conn(str(db_path)) as main_conn:
            with connection_repository.read_conn(str(db_path)) as reused_conn:
                assert reused_conn is main_conn

            result_queue = queue.Queue()

            def query_from_background_thread():
                try:
                    with connection_repository.read_conn(str(db_path)) as worker_conn:
                        result_queue.put(
                            (
                                worker_conn is main_conn,
                                worker_conn.execute(
                                    "SELECT value FROM samples"
                                ).fetchone()[0],
                            )
                        )
                except Exception as error:  # pragma: no cover - assertion reports it
                    result_queue.put(error)

            thread = threading.Thread(target=query_from_background_thread)
            thread.start()
            thread.join(timeout=5)

            assert not thread.is_alive()
            result = result_queue.get_nowait()
            assert not isinstance(result, Exception)
            assert result == (False, "ok")
    finally:
        connection_repository.close_shared_read_conn()


def test_close_shared_read_connection_resets_same_thread_reuse(tmp_path):
    db_path = tmp_path / "reset.db"
    sqlite3.connect(db_path).close()

    connection_repository.init_shared_read_conn(str(db_path))
    with connection_repository.read_conn(str(db_path)) as original:
        pass

    connection_repository.close_shared_read_conn()

    with connection_repository.read_conn(str(db_path)) as replacement:
        assert replacement is not original
