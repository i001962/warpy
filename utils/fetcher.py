from abc import ABC, abstractmethod
from typing import Tuple, List, Any, Dict, Optional, Union
import time
import requests
from utils.models import Reaction, Location, User, Cast, ExternalAddress, EthTransaction, ERC1155Metadata
import asyncio
import aiohttp
from datetime import datetime


class BaseFetcher(ABC):
    """
    BaseFetcher is an abstract base class for all Fetcher classes.
    It provides the basic structure for all fetchers including synchronous and asynchronous request functions.
    """

    @abstractmethod
    def fetch_data(self):
        """
        Abstract method to be implemented by child classes to fetch data from the respective sources.
        """
        pass

    @abstractmethod
    def get_models(self):
        """
        Abstract method to be implemented by child classes to return clean data models ready for insertion into the database.
        """
        pass

    @abstractmethod
    def _extract_data(self):
        """
        Abstract method to be implemented by child classes to extract relevant data from the raw data fetched.
        """
        pass

    def _make_request(self, url: str, headers: Dict[str, str] = None, timeout: int = 10) -> Any:
        """
        Makes a synchronous GET request to the specified URL, and returns the JSON response.

        :param url: The URL to send the request to.
        :param headers: Optional dictionary of headers to include in the request.
        :param timeout: Optional time limit in seconds for the request to complete.
        :return: Parsed JSON response.
        """
        print(f"Fetching from {url}")
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.json()

    async def _make_async_request(self, url: str, headers: Dict[str, str] = None, data: Any = None, method: str = "GET", timeout: int = 10) -> Any:
        """
        Makes an asynchronous request to the specified URL, and returns the JSON response.

        :param url: The URL to send the request to.
        :param headers: Optional dictionary of headers to include in the request.
        :param data: Optional data to include in the request body.
        :param method: Optional HTTP method to use (default is "GET").
        :param timeout: Optional time limit in seconds for the request to complete.
        :return: Parsed JSON response.
        """
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            print(f"Fetching from {url}")
            if method == "GET":
                async with session.get(url, headers=headers) as response:
                    response.raise_for_status()
                    return await response.json()
            elif method == "POST":
                async with session.post(url, headers=headers, json=data) as response:
                    response.raise_for_status()
                    return await response.json()
            else:
                raise ValueError(f"Invalid method: {method}")

    async def _make_async_request_with_retry(self, url: str, max_retries: int = 3, delay: int = 5, headers: Dict[str, str] = None, method: str = "GET", data: Any = None, timeout: int = 10) -> Optional[Any]:
        """
        Makes an asynchronous request to the specified URL with a retry mechanism.

        :param url: The URL to send the request to.
        :param max_retries: Maximum number of times to retry the request in case of a failure.
        :param delay: Time delay in seconds between retries.
        :param headers: Optional dictionary of headers to include in the request.
        :param method: HTTP method to use for the request (GET or POST).
        :param data: Optional data to include in the request body for POST requests.
        :param timeout: Optional time limit in seconds for the request to complete.
        :return: Parsed JSON response, or None if all retries fail.
        """
        retries = 0
        while retries < max_retries:
            try:
                response = await self._make_async_request(url, headers=headers, data=data, method=method, timeout=timeout)

                response_data = response
                if response_data:
                    return response_data
                else:
                    print(f"No results found for the URL: {url}. Retrying...")
            except (aiohttp.ClientResponseError, asyncio.TimeoutError) as e:
                print(f"Error occurred for URL {url}. Retrying...")
            await asyncio.sleep(delay)
            retries += 1

        print(
            f"Failed to fetch data from URL {url} after {max_retries} attempts.")
        return None


class WarpcastUserFetcher(BaseFetcher):
    """
    WarpcastUserFetcher is a concrete implementation of the BaseFetcher.
    It fetches recent user data from the Warpcast API.
    """

    def __init__(self, key: str):
        """
        Initializes WarpcastUserFetcher with an API key.

        :param key: str, API key to access the Warpcast API.
        """
        self.key = key

    def fetch_data(self) -> List[Dict[str, Any]]:
        """
        Fetches data for recent users from the Warpcast API.

        :return: A list of dictionaries containing user data.
        """
        all_data = []
        cursor = None

        while True:
            batch_data, cursor = self._fetch_batch(cursor)
            all_data.extend(batch_data)

            if cursor is None:
                break
            else:
                time.sleep(1)  # add a delay to avoid hitting rate limit

        return all_data

    def _fetch_batch(self, cursor: Optional[str] = None, limit: int = 1000) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Fetches a batch of user data from the Warpcast API with pagination.

        :param cursor: Optional, str, Cursor for pagination.
        :param limit: int, Maximum number of users to fetch in the batch.
        :return: A tuple containing a list of dictionaries with user data and the next cursor, if any.
        """
        url = f"https://api.warpcast.com/v2/recent-users?cursor={cursor}&limit={limit}" if cursor else f"https://api.warpcast.com/v2/recent-users?limit={limit}"
        json_data = self._make_request(
            url, headers={"Authorization": "Bearer " + self.key})
        return json_data["result"]['users'], json_data.get("next", {}).get('cursor') if json_data.get("next") else None

    def _extract_data(self, user: Dict[str, Any]) -> Tuple[User, Optional[Location]]:
        """
        Extracts relevant user data and location from a raw user dictionary.

        :param user: dict, Raw user data from the Warpcast API.
        :return: A tuple containing a User object and an optional Location object.
        """
        location_data = user.get('profile', {}).get('location', {})
        location = Location(
            id=location_data.get('placeId', ''),
            description=location_data.get('description', '')
        )

        user_data = User(
            fid=user['fid'],
            username=user['username'],
            display_name=user['displayName'],
            pfp_url=user['pfp']['url'] if 'pfp' in user else '',
            bio_text=user.get('profile', {}).get('bio', {}).get('text', ''),
            following_count=user.get('followingCount', 0),
            follower_count=user.get('followerCount', 0),
            location_id=location.id,
            verified=int(user['pfp']['verified']
                         ) if 'pfp' in user and 'verified' in user['pfp'] else 0,
            farcaster_address="",  # Update this value as needed
            registered_at=-1  # Update this value as needed
        )

        return user_data, location if location.id else None

    def get_models(self, users: List[Dict[str, Any]]) -> Tuple[List[User], List[Location]]:
        """
        Processes raw user data and returns lists of User and Location model objects.

        :param users: list, A list of dictionaries containing raw user data.
        :return: A tuple containing two lists: one of User objects and one of Location objects.
        """
        user_data = [self._extract_data(user) for user in users]

        user_list = [data[0] for data in user_data]
        location_list = [data[1] for data in user_data if data[1]]

        # Filter duplicates and remove None for locations
        location_list = list(
            {location.id: location for location in location_list}.values())

        return user_list, location_list


class SearchcasterFetcher(BaseFetcher):
    """
    SearchcasterFetcher is a concrete implementation of the BaseFetcher.
    It fetches user data from the Searchcaster API.
    """

    async def fetch_data(self, usernames: List[str]) -> List[Dict[str, Any]]:
        """
        Fetches user data from the Searchcaster API for a list of usernames.

        :param usernames: list, A list of usernames to fetch data for.
        :return: A list of dictionaries containing user data.
        """
        tasks = [asyncio.create_task(self._fetch_single_user(
            username)) for username in usernames]
        users = await asyncio.gather(*tasks)
        return users

    async def _fetch_single_user(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Fetches data for a single user from the Searchcaster API by username.

        :param username: str, Username to fetch data for.
        :return: A dictionary containing user data, or None if not found.
        """
        url = f'https://searchcaster.xyz/api/profiles?username={username}'

        response_data = await self._make_async_request_with_retry(url)
        return response_data[0] if response_data else None

    def _extract_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extracts relevant user data from a raw user dictionary.

        :param data: dict, Raw user data from the Searchcaster API.
        :return: A dictionary with the extracted user data.
        """
        return {
            'fid': data['body']['id'],
            'farcaster_address': data['body']['address'],
            'external_address': data['connectedAddress'],
            'registered_at': data['body']['registeredAt']
        }

    def get_models(self, users: List[User], user_data_list: List[Dict[str, Any]]) -> List[User]:
        """
        Updates User model objects with additional data fetched from the Searchcaster API.

        :param users: list, A list of User model objects to update.
        :param user_data_list: list, A list of dictionaries containing raw user data.
        :return: A list of updated User model objects.
        """

        updated_users = []

        extracted_user_data = [self._extract_data(
            user_data) for user_data in user_data_list]
        user_data_dict = {
            user_data['fid']: user_data for user_data in extracted_user_data}

        for user in users:
            user_data = user_data_dict.get(user.fid)
            if user_data and user_data['farcaster_address'] is not None and user_data['registered_at'] != 0:
                user.farcaster_address = user_data['farcaster_address']
                user.external_address = user_data['external_address']
                user.registered_at = user_data['registered_at']
                updated_users.append(user)

        return updated_users


class WarpcastReactionFetcher(BaseFetcher):
    """
    WarpcastReactionFetcher is a concrete implementation of the BaseFetcher.
    It fetches reaction data from the Warpcast API.
    """

    def __init__(self, key: str, n: int = 10):
        """
        Initializes a WarpcastReactionFetcher object.
        :param key: str, The Warpcast API key to use for fetching data.
        :param n: int, The number of reactions to fetch for each cast.
        """
        self.warpcast_hub_key = key
        self.n = n

    async def fetch_data(self, cast_hashes: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetches reaction data from the Warpcast API for a list of cast hashes.
        :param cast_hashes: list, A list of cast hashes to fetch data for.
        :return: A dictionary containing a list of reactions for each cast hash.
        """
        reactions = await self._get_cast_reactions_async(cast_hashes, self.warpcast_hub_key, self.n)
        return reactions

    def get_models(self, reactions: Dict[str, List[Dict[str, Any]]]) -> List[Reaction]:
        """
        Processes raw reaction data and returns a list of Reaction model objects.
        :param reactions: dict, A dictionary containing a list of reactions for each cast hash.
        :return: A list of Reaction model objects.
        """
        extracted_reactions = [
            self._extract_data(reaction)
            for reaction_list in reactions.values()
            for reaction in reaction_list
        ]
        return extracted_reactions

    def _extract_data(self, data: Dict[str, Any]) -> Reaction:
        """
        Extracts relevant reaction data from a raw reaction dictionary.
        :param data: dict, Raw reaction data from the Warpcast API.
        :return: A Reaction model object.
        """
        return Reaction(
            reaction_type=data['type'],
            hash=data['hash'],
            timestamp=data['timestamp'],
            target_hash=data['castHash'],
            author_fid=data['reactor']['fid'],
        )

    async def _get_cast_reactions_async(self, cast_hashes: List[str], warpcast_hub_key: str, n: int) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetches reaction data from the Warpcast API for a list of cast hashes.
        :param cast_hashes: list, A list of cast hashes to fetch data for.
        :param warpcast_hub_key: str, The Warpcast API key to use for fetching data.
        :param n: int, The number of reactions to fetch for each cast.
        :return: A dictionary containing a list of reactions for each cast hash.
        """
        headers = {"Authorization": f"Bearer {warpcast_hub_key}"}
        reactions = {}
        for i in range(0, len(cast_hashes), n):
            tasks = []
            for cast_hash in cast_hashes[i:i + n]:
                url = f"https://api.warpcast.com/v2/cast-reactions?castHash={cast_hash}&limit=100"
                tasks.append(self._fetch_reactions(url, headers))

            responses = await asyncio.gather(*tasks)
            for cast_hash, response_data in zip(cast_hashes[i:i + n], responses):
                if response_data is not None and response_data != []:
                    reactions[cast_hash] = response_data

        return reactions

    async def _fetch_reactions(self, url: str, headers: Dict[str, str]) -> List[Dict[str, Any]]:
        """
        Fetches reaction data from the Warpcast API for a single cast hash.
        :param url: str, The URL to fetch data from.
        :param headers: dict, The headers to use for the request.
        :return: A list of reaction data.
        """
        reactions = []
        cursor = None
        while True:
            try:
                url_with_cursor = f"{url}&cursor={cursor}" if cursor else url

                data = await self._make_async_request_with_retry(url_with_cursor, headers=headers)

                reactions.extend(data['result']['reactions'])

                cursor = data.get('next', {}).get('cursor')
                if cursor is None:
                    break

            except ValueError as e:
                print(f"Error occurred for {url}: {e}. Retrying...")
                await asyncio.sleep(5)

        return reactions


class EnsdataFetcher(BaseFetcher):
    async def fetch_data(self, addresses: List[str]) -> List[Dict[str, Any]]:
        users = await self._get_users_from_ensdata(addresses)
        return users

    def get_models(self, users: List[Dict[str, Any]]) -> List[ExternalAddress]:
        extracted_users = [
            self._extract_data(user)
            for user in users
        ]
        return extracted_users

    async def _get_single_user_from_ensdata(self, address: str) -> Dict[str, Any]:
        url = f'https://ensdata.net/{address}'
        json_data = await self._make_async_request_with_retry(url, max_retries=3, delay=5, timeout=10)
        return json_data if json_data else None

    async def _get_users_from_ensdata(self, addresses: List[str]) -> List[Dict[str, Any]]:
        tasks = [asyncio.create_task(self._get_single_user_from_ensdata(address))
                 for address in addresses]
        users = await asyncio.gather(*tasks)
        return list(filter(None, users))

    def _extract_data(self, data: Dict[str, Any]) -> ExternalAddress:
        return ExternalAddress(
            address=data.get('address'),
            ens=data.get('ens'),
            url=data.get('url'),
            github=data.get('github'),
            twitter=data.get('twitter'),
            telegram=data.get('telegram'),
            email=data.get('email'),
            discord=data.get('discord')
        )


class AlchemyTransactionFetcher(BaseFetcher):
    def __init__(self, key: str):
        self.base_url = f"https://eth-mainnet.g.alchemy.com/v2/{key}"
        self.transactions = []
        self.addresses = []

    async def fetch_data(self, addresses: List[str]):
        self.addresses = addresses
        latest_block_of_user = self._get_latest_block_of_user()

        # Fetch data concurrently using asyncio.gather
        tasks = [self._fetch_data_for_address(
            address, latest_block_of_user) for address in self.addresses]
        all_transactions = await asyncio.gather(*tasks)

        # Flatten the list of transactions and update self.transactions
        self.transactions = [
            transaction for sublist in all_transactions for transaction in sublist]

        return self.transactions

    async def _fetch_data_for_address(self, address: str, latest_block_of_user: int):
        transactions = []
        page_key = None
        while True:
            url, headers, payload = self._build_request_url_and_headers(
                latest_block_of_user, address, page_key)
            response_data = await self._make_async_request_with_retry(url, headers=headers, data=payload, method="POST")
            if not response_data:
                break

            page_key = response_data.get('result', {}).get('pageKey')
            transactions += response_data['result']['transfers']
            if page_key is None:
                break

        return transactions

    def get_models(self, transactions: List[Dict[str, Any]]) -> List[Union[EthTransaction, ERC1155Metadata]]:
        models = []
        for transaction in transactions:
            address = transaction.get('to') or transaction.get('from')
            if address not in self.addresses:
                continue

            eth_transaction, erc1155_metadata_objs = self._extract_data(
                transaction, address)
            models.append(eth_transaction)
            models.extend(erc1155_metadata_objs)

        return models

    def _extract_data(self, transaction: Dict[str, Any], address: str) -> Tuple[EthTransaction, List[ERC1155Metadata]]:
        eth_transaction = EthTransaction(
            hash=transaction['hash'],
            address_external=address,
            timestamp=int(datetime.strptime(
                transaction['metadata']['blockTimestamp'], '%Y-%m-%dT%H:%M:%S.%fZ').timestamp()) * 1000,
            block_num=int(transaction['blockNum'], 16),
            from_address=transaction['from'],
            to_address=transaction['to'],
            value=transaction['value'],
            erc721_token_id=transaction.get('erc721TokenId'),
            token_id=transaction.get('tokenId'),
            asset=transaction.get('asset'),
            category=transaction.get('category', "unknown")
        )

        erc1155_metadata_list = transaction.get('erc1155Metadata') or []
        erc1155_metadata_objs = []

        for metadata in erc1155_metadata_list:
            erc1155_metadata = ERC1155Metadata(
                eth_transaction_hash=transaction['hash'],
                token_id=metadata['tokenId'],
                value=metadata['value']
            )
            erc1155_metadata_objs.append(erc1155_metadata)

        return eth_transaction, erc1155_metadata_objs

    def _get_latest_block_of_user(self) -> int:
        # Replace this with your session/query to get the latest block of the user
        return 0

    def _build_request_url_and_headers(self, from_block: int, address: str, page_key: str = None) -> Tuple[str, Dict[str, str], Dict[str, Any]]:
        headers = {
            "accept": "application/json",
            "content-type": "application/json"
        }

        payload = {
            "id": 1,
            "jsonrpc": "2.0",
            "method": "alchemy_getAssetTransfers",
            "params": [
                {
                    "fromBlock": f"0x{from_block:x}",
                    "toBlock": "latest",
                    "toAddress": address,
                    "category": ["erc721", "erc1155", "erc20", "specialnft", "external"],
                    "withMetadata": True,
                    "excludeZeroValue": True,
                    "maxCount": "0x3e8",
                }
            ]
        }

        if page_key:
            payload['params'][0]['pageKey'] = page_key

        return self.base_url, headers, payload
