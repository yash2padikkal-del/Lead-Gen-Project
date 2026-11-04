import { NextResponse } from "next/server";
import JSZip from "jszip";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ artifactId: string }> }
) {
  try {
    const { artifactId } = await params;

    if (!/^\d+$/.test(artifactId)) {
      return NextResponse.json(
        { error: "Invalid artifact ID." },
        { status: 400 }
      );
    }

    const token = process.env.GITHUB_TOKEN;
    const owner = process.env.GITHUB_OWNER;
    const repo = process.env.GITHUB_REPO;

    if (!token || !owner || !repo) {
      return NextResponse.json(
        { error: "GitHub configuration is missing." },
        { status: 500 }
      );
    }

    const response = await fetch(
      `https://api.github.com/repos/${owner}/${repo}/actions/artifacts/${artifactId}/zip`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
        },
        cache: "no-store",
      }
    );

    if (!response.ok) {
      console.error(
        "GitHub artifact download failed:",
        response.status
      );

      return NextResponse.json(
        { error: "Unable to download the Excel export." },
        { status: response.status }
      );
    }

    const zipData = new Uint8Array(
      await response.arrayBuffer()
    );

    const zip = await JSZip.loadAsync(zipData);

    const excelFile = Object.values(zip.files).find(
      (file) =>
        !file.dir &&
        file.name.toLowerCase().endsWith(".xlsx")
    );

    if (!excelFile) {
      return NextResponse.json(
        { error: "No Excel workbook found in the artifact." },
        { status: 404 }
      );
    }

    const excelData = await excelFile.async("uint8array");

const filename =
  excelFile.name.split("/").pop() || "leadgen-export.xlsx";

const excelBuffer = Buffer.from(excelData);

return new NextResponse(excelBuffer, {
  status: 200,
  headers: {
    "Content-Type":
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "Content-Disposition": `attachment; filename="${filename}"`,
    "Content-Length": String(excelBuffer.length),
    "Cache-Control": "no-store",
  },
});

  } catch (error) {
    console.error("Excel download error:", error);

    return NextResponse.json(
      { error: "An unexpected download error occurred." },
      { status: 500 }
    );
  }
}