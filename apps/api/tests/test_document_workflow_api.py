from io import BytesIO

from fastapi.testclient import TestClient
from pptx import Presentation
from pptx.util import Inches
from pypdf import PdfWriter

from app.main import MAX_DOCUMENT_UPLOAD_BYTES
from tests.conftest import bootstrap, invite_and_accept
from tests.test_campaign_packages import campaign_payload, create_assets


def make_pdf() -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(output)
    return output.getvalue()


def make_pptx(text: str = "Traceable harvest story") -> bytes:
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    slide.shapes.add_textbox(Inches(1), Inches(1), Inches(8), Inches(1)).text = text
    output = BytesIO()
    presentation.save(output)
    return output.getvalue()


def test_document_preview_requires_write_role(
    client: TestClient,
    auth: dict[str, str],
) -> None:
    _, viewer = invite_and_accept(
        client,
        auth,
        "viewer-document@example.com",
        "viewer",
        "viewer-password",
    )
    viewer_auth = {"Authorization": f"Bearer {viewer['access_token']}"}

    unauthorized = client.post(
        "/v1/document-imports/preview",
        files={"file": ("source.pptx", make_pptx())},
    )
    forbidden = client.post(
        "/v1/document-imports/preview",
        headers=viewer_auth,
        files={"file": ("source.pptx", make_pptx())},
    )

    assert unauthorized.status_code == 401
    assert forbidden.status_code == 403


def test_pptx_document_preview_returns_editable_text_and_provenance(
    client: TestClient,
    auth: dict[str, str],
) -> None:
    response = client.post(
        "/v1/document-imports/preview",
        headers=auth,
        files={
            "file": (
                "field-notes.pptx",
                make_pptx(),
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["filename"] == "field-notes.pptx"
    assert payload["text"] == "Traceable harvest story"
    assert payload["sections"] == [
        {
            "kind": "slide",
            "number": 1,
            "label": "Slide 1",
            "text": "Traceable harvest story",
        }
    ]
    assert len(payload["content_sha256"]) == 64


def test_document_preview_reports_detected_type_when_filename_has_no_extension(
    client: TestClient,
    auth: dict[str, str],
) -> None:
    response = client.post(
        "/v1/document-imports/preview",
        headers=auth,
        files={"file": ("uploaded-document", make_pdf(), "application/octet-stream")},
    )

    assert response.status_code == 200, response.text
    assert response.json()["media_type"] == "application/pdf"


def test_document_preview_rejects_unsupported_corrupt_and_large_files(
    client: TestClient,
    auth: dict[str, str],
) -> None:
    unsupported = client.post(
        "/v1/document-imports/preview",
        headers=auth,
        files={"file": ("source.docx", b"not-supported")},
    )
    corrupt = client.post(
        "/v1/document-imports/preview",
        headers=auth,
        files={"file": ("source.pdf", b"%PDF-not-valid", "application/pdf")},
    )
    too_large = client.post(
        "/v1/document-imports/preview",
        headers=auth,
        files={"file": ("source.pdf", b"x" * (MAX_DOCUMENT_UPLOAD_BYTES + 1))},
    )

    assert unsupported.status_code == 415
    assert corrupt.status_code == 422
    assert too_large.status_code == 413


def test_pdf_document_preview_reports_blank_scanned_style_document(
    client: TestClient,
    auth: dict[str, str],
) -> None:
    response = client.post(
        "/v1/document-imports/preview",
        headers=auth,
        files={"file": ("blank.pdf", make_pdf(), "application/pdf")},
    )

    assert response.status_code == 200, response.text
    assert response.json()["text"] == ""
    assert any("no extractable text" in item.lower() for item in response.json()["warnings"])


def test_campaign_presentation_download_is_editable_and_tenant_scoped(
    client: TestClient,
    auth: dict[str, str],
) -> None:
    brand, product = create_assets(client, auth)
    campaign_response = client.post(
        "/v1/campaign-packages",
        headers=auth,
        json=campaign_payload(brand, product),
    )
    assert campaign_response.status_code == 201, campaign_response.text
    campaign = campaign_response.json()

    download = client.get(
        f"/v1/campaign-packages/{campaign['id']}/presentation",
        headers=auth,
    )

    assert download.status_code == 200, download.text
    assert download.content.startswith(b"PK")
    assert (
        download.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
    presentation = Presentation(BytesIO(download.content))
    assert len(presentation.slides) == 5
    deck_text = "\n".join(
        shape.text
        for slide in presentation.slides
        for shape in slide.shapes
        if getattr(shape, "has_text_frame", False)
    )
    assert campaign["title"] in deck_text
    assert brand["name"] in deck_text
    assert product["name"] in deck_text
    assert "草稿" in deck_text
    assert "请勿直接发布" in deck_text

    second = bootstrap(client, "presentation-second", "presentation-second@example.com")
    second_auth = {"Authorization": f"Bearer {second['access_token']}"}
    hidden = client.get(
        f"/v1/campaign-packages/{campaign['id']}/presentation",
        headers=second_auth,
    )
    assert hidden.status_code == 404
