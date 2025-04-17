export default async function handler(req, res) {
    const base_id = req.query.base_id || 'appGSg5QfDNKgFf73';
    const table_id = req.query.table_id || 'tblnR438TK52Gr0HB';
    
    try {
      const response = await fetch(`https://api.airtable.com/v0/${base_id}/${table_id}`, {
        headers: {
          'Authorization': `Bearer ${process.env.AIRTABLE_API_KEY}`,
          'Content-Type': 'application/json'
        }
      });
      
      const data = await response.json();
      res.status(200).json(data);
    } catch (error) {
      res.status(500).json({ error: 'Failed to fetch data' });
    }
  }
