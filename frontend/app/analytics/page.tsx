import PageStub from "../components/PageStub";

export default function AnalyticsPage() {
  return (
    <PageStub
      breadcrumb="Operations"
      title="Analytics"
      summary="Classifier accuracy, confidence distributions, and category trends over time."
      sections={[
        { title: "Accuracy", body: "Per-class precision and recall, and the human correction rate." },
        { title: "Confidence", body: "Distribution of model confidence per decision." },
        { title: "Throughput", body: "Items per hour, inference latency, and camera uptime." },
      ]}
    />
  );
}
