const { verifyToken } = require('@clerk/backend');

const GITHUB_OWNER  = process.env.GITHUB_REPO_OWNER || 'devrenanoliveira';
const GITHUB_REPO   = process.env.GITHUB_REPO_NAME  || 'acionamentos-zon';
const GITHUB_BRANCH = process.env.GITHUB_BRANCH     || 'main';

const AUTHORIZED_EMAILS = (process.env.AUTHORIZED_EMAILS || '')
  .split(',').map(s => s.trim().toLowerCase()).filter(Boolean);
const AUTHORIZED_DOMAINS = (process.env.AUTHORIZED_EMAIL_DOMAINS || '')
  .split(',').map(s => s.trim().toLowerCase()).filter(Boolean);

function emailAutorizado(email) {
  if (!email) return false;
  email = email.toLowerCase();
  if (AUTHORIZED_EMAILS.includes(email)) return true;
  const dominio = email.split('@')[1];
  return AUTHORIZED_DOMAINS.includes(dominio);
}

// Projeto #5 tem varios arquivos (nao um data.json so): index.json + um par
// {mes}.json/{mes}-analitico.json por mes. O parametro ?file= escolhe qual,
// mas so aceita esses formatos exatos - nunca um caminho arbitrario do repo.
const ARQUIVO_PERMITIDO = /^(index\.json|\d{4}-\d{2}(-analitico)?\.json)$/;

module.exports = async function handler(req, res) {
  if (req.method !== 'GET') {
    res.status(405).json({ error: 'Método não permitido.' });
    return;
  }

  const arquivo = req.query.file || 'index.json';
  if (!ARQUIVO_PERMITIDO.test(arquivo)) {
    res.status(400).json({ error: 'Arquivo inválido.' });
    return;
  }

  const authHeader = req.headers.authorization || '';
  const token = authHeader.startsWith('Bearer ') ? authHeader.slice(7) : null;

  if (!token) {
    res.status(401).json({ error: 'Não autenticado.' });
    return;
  }

  let payload;
  try {
    payload = await verifyToken(token, {
      secretKey: process.env.CLERK_SECRET_KEY,
      authorizedParties: (process.env.CLERK_AUTHORIZED_PARTIES || '')
        .split(',').map(s => s.trim()).filter(Boolean),
    });
  } catch (err) {
    res.status(401).json({ error: 'Sessão inválida ou expirada.' });
    return;
  }

  // payload.email só existe se o claim customizado "email" foi adicionado ao
  // session token no Clerk Dashboard (Sessions → Customize session token,
  // {{user.primary_email_address}}) — mesmo app Clerk do zon-dashboard-powered,
  // então se já foi configurado lá, já vale aqui também.
  if (!emailAutorizado(payload.email)) {
    res.status(403).json({ error: 'Este e-mail não tem acesso a este dashboard. Se você acha que deveria ter, fale com quem administra o acesso.' });
    return;
  }

  try {
    const ghResp = await fetch(
      `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/contents/data/${arquivo}?ref=${GITHUB_BRANCH}`,
      {
        headers: {
          Authorization: `Bearer ${process.env.GITHUB_TOKEN}`,
          Accept: 'application/vnd.github+json',
          'User-Agent': 'acionamentos-zon-api',
        },
      }
    );

    if (!ghResp.ok) {
      throw new Error('GitHub API respondeu ' + ghResp.status);
    }

    const meta = await ghResp.json();
    // Contents API só traz "content" inline para arquivos até 1MB.
    const jsonText = Buffer.from(meta.content, 'base64').toString('utf-8');
    const data = JSON.parse(jsonText);

    res.setHeader('Cache-Control', 'no-store');
    res.status(200).json(data);
  } catch (err) {
    console.error('Erro ao buscar ' + arquivo + ' do GitHub:', err);
    res.status(502).json({ error: 'Erro ao carregar dados.' });
  }
};
