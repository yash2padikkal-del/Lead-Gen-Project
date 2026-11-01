import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

interface AirtableRecord {
id: string;
createdTime: string;
fields: Record<string, unknown>;
}

export async function GET() {
const apiKey = process.env.AIRTABLE_API_KEY;
const baseId = process.env.AIRTABLE_BASE_ID;
const tableName = process.env.AIRTABLE_TABLE_NAME;

if (!apiKey || !baseId || !tableName) {
return NextResponse.json(
{ error: "Airtable configuration missing" },
{ status: 500 }
);
}

try {
const records: AirtableRecord[] = [];
let offset: string | undefined;


do {
  const url = new URL(
    `https://api.airtable.com/v0/${baseId}/${encodeURIComponent(tableName)}`
  );

  url.searchParams.set("pageSize", "100");

  if (offset) {
    url.searchParams.set("offset", offset);
  }

  const response = await fetch(url.toString(), {
    headers: {
      Authorization: `Bearer ${apiKey}`,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Airtable returned ${response.status}`);
  }

  const data: {
    records: AirtableRecord[];
    offset?: string;
  } = await response.json();

  records.push(...data.records);
  offset = data.offset;

} while (offset);

const leads = records.map((record) => ({
  id: record.id,
  createdTime: record.createdTime,
  name: record.fields["Lead Name"] || "Unknown",
  company: record.fields["Company"] || "Unknown",
  source: record.fields["Lead Source"] || "Unknown",
  contact: record.fields["Contact Information"] || "",
  score: Number(record.fields["Lead Score"] || 0),
  notes: record.fields["Notes"] || "",
  autoSourced: record.fields["Auto-Sourced"] || false,
}));

return NextResponse.json({
  success: true,
  total: leads.length,
  leads,
});


} catch (error) {
console.error("Airtable connection failed:", error);


return NextResponse.json(
  { error: "Failed to retrieve Airtable records" },
  { status: 500 }
);


}
}
