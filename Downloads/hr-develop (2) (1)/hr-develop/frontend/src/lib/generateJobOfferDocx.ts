import {
  Document,
  Packer,
  Paragraph,
  TextRun,
  ImageRun,
  Header,
  Footer,
  AlignmentType,
  PageNumber,
  TabStopType,
  TabStopPosition,
} from "docx";

export interface JobOfferData {
  title: string;
  experience_required: string;
  activities: string[];
  technical_skills: string[];
  behavioral_skills: string[];
}

const BRAND_BLUE = "2E75B6";

async function fetchImageBuffer(path: string): Promise<ArrayBuffer> {
  const response = await fetch(path);
  return response.arrayBuffer();
}

function bulletParagraph(text: string): Paragraph {
  return new Paragraph({
    bullet: { level: 0 },
    spacing: { after: 120, line: 300, lineRule: "auto" },
    indent: { left: 360 },
    children: [new TextRun({ text, size: 22 })],
  });
}

function bodyParagraph(text: string): Paragraph {
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED,
    spacing: { after: 200, line: 300, lineRule: "auto" },
    children: [new TextRun({ text, size: 22 })],
  });
}

export async function generateJobOfferDocx(data: JobOfferData): Promise<void> {
  const [diamondLogo, wordmarkLogo] = await Promise.all([
    fetchImageBuffer("/sofrecom-logo.png"),
    fetchImageBuffer("/logo.png"),
  ]);

  const header = new Header({
    children: [
      new Paragraph({
        alignment: AlignmentType.RIGHT,
        children: [
          new ImageRun({
            type: "png",
            data: diamondLogo,
            transformation: { width: 95, height: 108 },
          }),
        ],
      }),
    ],
  });

  const footer = new Footer({
    children: [
      new Paragraph({
        tabStops: [
          { type: TabStopType.RIGHT, position: TabStopPosition.MAX },
        ],
        children: [
          new ImageRun({
            type: "png",
            data: wordmarkLogo,
            transformation: { width: 106, height: 48 },
          }),
          new TextRun({ text: "\t" }),
          new TextRun({
            children: [PageNumber.CURRENT],
            size: 18,
            color: "808080",
          }),
        ],
      }),
    ],
  });

  const doc = new Document({
    background: { color: "F5F8FA" },
    styles: {
      default: {
        document: {
          run: { font: "Calibri", size: 22, color: "1A1A1A" },
        },
      },
    },
    sections: [
      {
        headers: { default: header },
        footers: { default: footer },
        properties: {
          page: {
            margin: { top: 1417, bottom: 1417, left: 1417, right: 1417 },
          },
        },
        children: [
          new Paragraph({
            spacing: { after: 240 },
            children: [
              new TextRun({
                text: data.title,
                bold: true,
                italics: true,
                size: 46,
                color: BRAND_BLUE,
              }),
            ],
          }),
          bodyParagraph(
            "Sofrecom, filiale du groupe Orange, a développé depuis plus de 50 ans un savoir-faire unique dans les métiers de l'opérateur, qui en fait aujourd'hui l'un des leaders mondiaux du conseil et de l'ingénierie. Ces dernières années, plus de 200 acteurs majeurs, dans plus de 100 pays, ont confié à Sofrecom la conduite de leurs projets stratégiques et opérationnels : transformation et optimisation, modernisation technologique, innovation et développement. Son accès privilégié aux expertises et à l'innovation du Groupe Orange permet à Sofrecom de proposer à ses clients des solutions d'avant-garde qui ont fait leurs preuves."
          ),
          bodyParagraph(
            "Sofrecom est une entreprise internationale riche de sa diversité, avec plus de 1500 consultants et experts répartis dans 11 implantations à travers le monde et issus de plus de 30 nationalités. Sofrecom est avant tout un réseau d'hommes et de femmes, un puissant réseau de savoir-faire et d'expertises qui relie ses clients, les experts Orange, ses partenaires industriels et locaux."
          ),
          bodyParagraph(
            "Lancée en novembre 2011, Sofrecom Tunisie compte aujourd'hui plus de 1000 ingénieurs et étend la présence de Sofrecom sur la zone Afrique du Nord et Moyen-Orient afin de répondre à une demande croissante de solutions dédiées et compétitives. Centre de développement et d'expertise pour les plates-formes de services et le Système d'Information, Sofrecom Tunisie s'inscrit en complémentarité des domaines d'activité des autres implantations de Sofrecom dans la région et permettra aux clients du groupe Sofrecom de bénéficier des synergies entre nos filiales."
          ),
          new Paragraph({
            spacing: { after: 300 },
            children: [
              new TextRun({
                text: "Sofrecom, the Know-How Network.",
                italics: true,
                bold: true,
                size: 22,
              }),
            ],
          }),

          new Paragraph({
            spacing: { before: 120, after: 160 },
            children: [
              new TextRun({
                text: "Activités principales",
                bold: true,
                size: 32,
                color: BRAND_BLUE,
              }),
            ],
          }),
          new Paragraph({
            spacing: { after: 120, line: 300, lineRule: "auto" },
            children: [
              new TextRun({ text: "Votre mission sera la suivante :", size: 22 }),
            ],
          }),
          ...data.activities.map((a) => bulletParagraph(a)),

          new Paragraph({
            spacing: { before: 240, after: 160 },
            children: [
              new TextRun({
                text: "Compétences requises",
                bold: true,
                size: 32,
                color: BRAND_BLUE,
              }),
            ],
          }),
          bodyParagraph(data.experience_required),
          new Paragraph({
            spacing: { after: 120 },
            children: [
              new TextRun({
                text: "Compétences techniques exigées",
                bold: true,
                underline: {},
                size: 24,
              }),
            ],
          }),
          ...data.technical_skills.map((s) => bulletParagraph(s)),

          new Paragraph({
            spacing: { before: 200, after: 120 },
            children: [
              new TextRun({
                text: "Aptitudes relationnelles et comportementales",
                bold: true,
                underline: {},
                size: 24,
              }),
            ],
          }),
          ...data.behavioral_skills.map((s) => bulletParagraph(s)),
        ],
      },
    ],
  });

  const blob = await Packer.toBlob(doc);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${data.title || "Offre_Emploi"}.docx`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
