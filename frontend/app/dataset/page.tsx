import PageStub from "../components/PageStub";

export default function DatasetPage() {
  return (
    <PageStub
      breadcrumb="Operations"
      title="Dataset"
      summary="Labeled examples captured from the live stream, available for export."
      sections={[
        { title: "Collected", body: "Examples auto-captured above the confidence threshold." },
        { title: "Review queue", body: "Low-confidence detections pending human correction." },
        { title: "Export", body: "COCO, YOLO, or raw image + JSON pairs." },
      ]}
    />
  );
}
