def test_default_config_uses_data_directory(tmp_path):
    from sc_gr_app.config import default_config

    config = default_config(tmp_path)

    assert config.db_path == tmp_path / "data" / "sc_gr.sqlite3"
    assert config.lock_dir == tmp_path / "data" / "locks"
    assert config.busy_timeout_ms == 5000
