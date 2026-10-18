def test_review_link_and_comments(client, user, upload, guest):
    h = user["headers"]
    f = upload(h)
    r = client.post("/api/review-links", headers=h, json={"file_id": f["id"], "title": "Draft contract"})
    assert r.status_code == 201
    link = r.json()
    token = link["token"]
    assert link["url"].endswith(f"/review/{token}")
    assert client.get("/api/review-links", headers=h).json()["links"][0]["id"] == link["id"]

    # Anyone with the link: no account or guest token needed.
    assert client.get(f"/api/public/review/{token}").json()["title"] == "Draft contract"
    assert client.get(f"/api/public/review/{token}/document").content.startswith(b"%PDF")
    c1 = client.post(f"/api/public/review/{token}/comments", json={"author": "Kumar", "text": "Fix clause 3", "page": 0, "x": 100, "y": 200})
    assert c1.status_code == 201
    c2 = client.post(f"/api/public/review/{token}/comments", json={"author": "Lata", "text": "Agreed", "parent_id": c1.json()["id"]})
    assert c2.status_code == 201
    assert client.post(f"/api/public/review/{token}/comments", json={"author": "X", "text": "y", "parent_id": 999999}).status_code == 400

    all_comments = client.get(f"/api/public/review/{token}/comments").json()["comments"]
    assert len(all_comments) == 2
    newer = client.get(f"/api/public/review/{token}/comments?since={c1.json()['id']}").json()["comments"]
    assert [c["author"] for c in newer] == ["Lata"]
    r = client.post(f"/api/public/review/{token}/comments/{c1.json()['id']}/resolve")
    assert r.json()["resolved"] is True
    assert c1.json()["id"] in client.get(f"/api/public/review/{token}/comments").json()["resolved_ids"]

    # Guests cannot create links; owners can disable them.
    assert client.post("/api/review-links", headers=guest, json={"file_id": f["id"]}).status_code == 401
    assert client.delete(f"/api/review-links/{link['id']}", headers=h).status_code == 204
    assert client.get(f"/api/public/review/{token}").status_code == 404
