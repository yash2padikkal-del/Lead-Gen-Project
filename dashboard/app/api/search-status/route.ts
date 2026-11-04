import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);

    const requestId = searchParams.get("requestId");

    if (!requestId) {
      return NextResponse.json(
        { error: "Missing request ID." },
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

    const headers = {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    };

    // Find the workflow run by its unique request ID.
    const runsResponse = await fetch(
      `https://api.github.com/repos/${owner}/${repo}/actions/runs?per_page=20`,
      {
        headers,
        cache: "no-store",
      }
    );

    if (!runsResponse.ok) {
      throw new Error("Unable to retrieve GitHub workflow runs.");
    }

    const runsData = await runsResponse.json();

    const run = runsData.workflow_runs?.find(
      (item: {
        display_title?: string;
        run_name?: string;
        id: number;
        status: string;
        conclusion: string | null;
        html_url: string;
      }) =>
        item.display_title?.includes(requestId) ||
        item.run_name?.includes(requestId)
    );

    if (!run) {
      return NextResponse.json({
        success: true,
        status: "queued",
        message: "Waiting for GitHub Actions to start.",
      });
    }

    const completed = run.status === "completed";

    if (!completed) {
      return NextResponse.json({
        success: true,
        status: run.status,
        message: "Your search is being processed.",
        runUrl: run.html_url,
      });
    }

    if (run.conclusion !== "success") {
      return NextResponse.json({
        success: true,
        status: "failed",
        message: `Search ${run.conclusion}.`,
        runUrl: run.html_url,
      });
    }

    // Find the Excel artifact belonging to this workflow run.
    const artifactsResponse = await fetch(
      `https://api.github.com/repos/${owner}/${repo}/actions/runs/${run.id}/artifacts`,
      {
        headers,
        cache: "no-store",
      }
    );

    if (!artifactsResponse.ok) {
      throw new Error("Unable to retrieve workflow artifacts.");
    }

    const artifactsData = await artifactsResponse.json();

    const artifact = artifactsData.artifacts?.find(
      (item: { name: string; expired: boolean }) =>
        item.name.startsWith("leadgen-export-") &&
        !item.expired
    );

    return NextResponse.json({
      success: true,
      status: "completed",
      message: "Your search has finished.",
      runUrl: run.html_url,
      artifactAvailable: Boolean(artifact),
      artifactId: artifact?.id ?? null,
    });

  } catch (error) {
    console.error("Search status error:", error);

    return NextResponse.json(
      { error: "Unable to retrieve search status." },
      { status: 500 }
    );
  }
}